import { Database } from "bun:sqlite";
import { closeSync, existsSync, mkdirSync, openSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@oh-my-pi/pi-coding-agent";

const home = homedir();
const storeDir = join(process.env.XDG_DATA_HOME || join(home, ".local", "share"), "mindie-agent", "omp");
const storePath = join(storeDir, "experience.sqlite3");
const adapterConfig = process.env.MINDIE_AGENT_CONFIG || join(
	process.env.MINDIE_CONFIG_HOME || join(process.env.XDG_CONFIG_HOME || join(home, ".config"), "mindie-agent"),
	"codex.json",
);
const launcher = join(process.env.CODEX_HOME || join(home, ".codex"), "plugins", "data", "mindie-agent-mindie-agent", "hook_launcher.py");
const worker = join(import.meta.dir, "experience.py");
const maxCaptureBytes = 256 * 1024;

interface Scope {
	workspace: string;
	revision: string | null;
	scanner: string | null;
}

interface Turn {
	session: string;
	previous: string | null;
	cwd: string;
	scope: Scope;
}

function openStore(write = false): Database | undefined {
	if (!existsSync(storePath)) return undefined;
	const db = new Database(storePath, { readonly: !write });
	if (write) db.exec("PRAGMA busy_timeout = 1500");
	return db;
}

function createStore(): Database {
	mkdirSync(storeDir, { recursive: true, mode: 0o700 });
	closeSync(openSync(storePath, "a", 0o600));
	const db = openStore(true)!;
	try {
		db.exec(`
			CREATE TABLE IF NOT EXISTS scopes (
				workspace TEXT PRIMARY KEY, revision TEXT, scanner TEXT
			) STRICT;
			CREATE TABLE IF NOT EXISTS experience (
				workspace TEXT NOT NULL, id TEXT NOT NULL, recorded_at INTEGER NOT NULL, body TEXT NOT NULL,
				PRIMARY KEY (workspace, id)
			) STRICT;
		`);
		return db;
	} catch (error) {
		db.close();
		throw error;
	}
}

function scopeAt(db: Database, cwd: string): Scope | null {
	return db.query<Scope, [string]>(`
		SELECT workspace, revision, scanner FROM scopes
		WHERE workspace = ?1 OR instr(?1, rtrim(workspace, '/') || '/') = 1
		ORDER BY length(workspace) DESC LIMIT 1
	`).get(cwd);
}

async function runWorker(args: string[], signal: AbortSignal, data?: Buffer): Promise<string> {
	const { python } = await Bun.file(adapterConfig).json();
	if (typeof python !== "string" || !isAbsolute(python)) throw new Error("MindIE runtime binding has no Python interpreter");
	signal.throwIfAborted();
	const child = Bun.spawn([python, "-IB", worker, ...args], {
		stdin: data ?? "ignore",
		stdout: "pipe",
		stderr: "pipe",
		signal,
	});
	const [code, output, error] = await Promise.all([child.exited, child.stdout.text(), child.stderr.text()]);
	if (code !== 0) throw new Error(error.trim() || `MindIE worker exited with code ${code}`);
	return output;
}

function visibleText(content: string | readonly { type: string; text?: string }[]): string {
	if (typeof content === "string") return content.trim();
	return content.flatMap(block => block.type === "text" && block.text ? [block.text] : []).join("\n").trim();
}

function humanPrompt(ctx: ExtensionContext, previous: string | null) {
	const manager = ctx.sessionManager;
	let entry = manager.getLeafEntry();
	let prompt: { id: string; text: string } | undefined;
	while (entry && entry.id !== previous) {
		if (!prompt && entry.type === "message" && entry.message.role === "user" && !entry.message.synthetic && !entry.message.parentIrc) {
			const text = visibleText(entry.message.content);
			if (text) prompt = { id: entry.id, text };
		}
		entry = entry.parentId ? manager.getEntry(entry.parentId) : undefined;
	}
	return previous === null || entry?.id === previous ? prompt : undefined;
}

export default function mindieAgent(pi: ExtensionAPI) {
	let pending: Turn | undefined;

	pi.on("session_start", async (_event, ctx) => {
		const result = await pi.exec("python3", ["-IB", launcher, "session-start"], { signal: AbortSignal.timeout(5000) });
		if (result.code !== 0) ctx.ui.notify(`MindIE maintenance request failed (${result.code})`, "warning");
	});

	pi.on("session_switch", () => { pending = undefined; });
	pi.on("session_clear", () => { pending = undefined; });
	pi.on("before_agent_start", (event, ctx) => {
		pending = undefined;
		if (event.reason !== "prompt" || !ctx.sessionManager.getSessionFile()) return;
		using db = openStore();
		if (!db) return;
		const cwd = realpathSync(ctx.cwd);
		const scope = scopeAt(db, cwd);
		if (scope?.revision && scope.scanner) pending = {
			session: ctx.sessionManager.getSessionId(), previous: ctx.sessionManager.getLeafId(), cwd, scope,
		};
	});

	pi.on("session_stop", async (event, ctx) => {
		const turn = pending;
		pending = undefined;
		const answer = event.last_assistant_message;
		if (!turn || !turn.scope.scanner || event.stop_hook_active || !event.session_file || event.signal.aborted ||
			turn.session !== event.session_id || answer?.role !== "assistant" || answer.stopReason !== "stop") return;
		try {
			if (realpathSync(ctx.cwd) !== turn.cwd) return;
			using db = openStore(true);
			if (!db || scopeAt(db, turn.cwd)?.revision !== turn.scope.revision) return;
			const prompt = humanPrompt(ctx, turn.previous);
			const reply = visibleText(answer.content);
			if (!prompt || !reply) return;
			const raw = `## User\n\n${prompt.text}\n\n## Assistant\n\n${reply}`;
			if (Buffer.byteLength(raw) > maxCaptureBytes) {
				ctx.ui.notify("MindIE local capture exceeded 256 KiB", "warning");
				return;
			}
			const signal = AbortSignal.any([event.signal, AbortSignal.timeout(10000)]);
			const quoted = await runWorker(["redact", turn.scope.scanner, turn.scope.workspace, String(maxCaptureBytes)], signal, Buffer.from(raw));
			const body = JSON.parse(quoted);
			if (typeof body !== "string") throw new Error("MindIE redactor returned an invalid result");
			if (signal.aborted) return;
			// A permission change in any omp process wins until this transaction commits.
			db.transaction(() => {
				const current = scopeAt(db, turn.cwd);
				if (current?.revision !== turn.scope.revision || current?.workspace !== turn.scope.workspace) return;
				db.query("INSERT OR IGNORE INTO experience VALUES (?, ?, ?, ?)").run(
					current.workspace, `${event.session_id}:${prompt.id}`, Date.now(), body,
				);
			}).immediate();
		} catch (error) {
			if (!event.signal.aborted) ctx.ui.notify(`MindIE local capture failed: ${error instanceof Error ? error.message : String(error)}`, "warning");
		}
	});

	pi.registerCommand("mindie-capture", {
		description: "Manage local MindIE experience capture for this working directory (on, off, status)",
		async handler(args, ctx) {
			const action = args.trim() || "status";
			if (action !== "on" && action !== "off" && action !== "status") {
				ctx.ui.notify("Usage: /mindie-capture on|off|status", "warning");
				return;
			}
			const cwd = realpathSync(ctx.cwd);
			if (action === "on") {
				const scanner = (await runWorker(["install-scanner", join(storeDir, "cache", "gitleaks")], AbortSignal.timeout(40000))).trim();
				if (!isAbsolute(scanner) || !existsSync(scanner)) throw new Error("MindIE scanner installation returned no executable");
				using db = createStore();
				db.query("INSERT OR REPLACE INTO scopes VALUES (?, ?, ?)").run(cwd, crypto.randomUUID(), scanner);
				ctx.ui.notify(`MindIE local capture enabled for ${cwd}`, "info");
				return;
			}
			using db = openStore(action === "off");
			const scope = db ? scopeAt(db, cwd) : null;
			if (action === "off" && db && scope?.revision) db.query("INSERT OR REPLACE INTO scopes VALUES (?, NULL, NULL)").run(cwd);
			const workspace = action === "off" ? cwd : scope?.workspace ?? cwd;
			ctx.ui.notify(`MindIE local capture ${action === "status" && scope?.revision ? "enabled" : "disabled"} for ${workspace}`, "info");
		},
	});

	const Type = pi.typebox.Type;
	pi.registerTool({
		name: "mindie_local_search",
		label: "MindIE Local Experience",
		description: "Search redacted MindIE experience previously captured in this working directory. Use a concrete keyword or identifier.",
		parameters: Type.Object({ query: Type.String({ minLength: 1, maxLength: 200 }) }),
		async execute(_id, { query }, _signal, _onUpdate, ctx) {
			const term = query.trim();
			if (!term) throw new Error("Enter a non-empty search term");
			using db = openStore();
			const scope = db ? scopeAt(db, realpathSync(ctx.cwd)) : null;
			const hits = scope && db ? db.query<{ excerpt: string }, [string, string]>(`
				SELECT substr(body, max(1, instr(lower(body), lower(?1)) - 320), 1800) AS excerpt
				FROM experience WHERE workspace = ?2 AND instr(lower(body), lower(?1)) > 0
				ORDER BY recorded_at DESC LIMIT 5
			`).all(term, scope.workspace) : [];
			return {
				content: [{ type: "text", text: hits.length ? hits.map(hit => hit.excerpt).join("\n\n---\n\n") : "No matching local MindIE experience in this workspace." }],
				details: { matches: hits.length },
			};
		},
	});
}
