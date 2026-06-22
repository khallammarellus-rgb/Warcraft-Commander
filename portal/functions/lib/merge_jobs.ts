import { loadLobby } from "./eo_lobby";

export type MergeJobStatus = "pending" | "running" | "complete" | "failed";

export interface MergeJob {
  id: string;
  game_id: string;
  campaign_id: string;
  variant: string;
  turn: number;
  cell: "blue-cell" | "red-cell";
  canonical_name: string;
  r2_key: string;
  theater?: string;
  status: MergeJobStatus;
  requested_at: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  deploy_url?: string;
  triggered_by: "auto" | "manual";
  board_refresh_hint?: string;
}

export interface MergeLatestSummary {
  job_id: string;
  status: MergeJobStatus;
  canonical_name?: string;
  completed_at?: string;
  error?: string;
  triggered_by?: "auto" | "manual";
}

export interface BoardRefreshNotice {
  at: string;
  canonical_name: string;
  job_id: string;
}

export function mergeJobKey(id: string): string {
  return `merge_job:${id}`;
}

export function mergeLatestKey(gameId: string): string {
  return `merge_latest:${gameId}`;
}

export function mergePendingIndexKey(): string {
  return "merge_jobs:pending";
}

export function boardRefreshKey(gameId: string): string {
  return `board_refresh:${gameId}`;
}

function randomJobId(): string {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function loadMergeJob(kv: KVNamespace, id: string): Promise<MergeJob | null> {
  const raw = await kv.get(mergeJobKey(id));
  if (!raw) return null;
  return JSON.parse(raw) as MergeJob;
}

export async function saveMergeJob(kv: KVNamespace, job: MergeJob): Promise<void> {
  await kv.put(mergeJobKey(job.id), JSON.stringify(job));
  const summary: MergeLatestSummary = {
    job_id: job.id,
    status: job.status,
    canonical_name: job.canonical_name,
    completed_at: job.completed_at,
    error: job.error,
    triggered_by: job.triggered_by,
  };
  await kv.put(mergeLatestKey(job.game_id), JSON.stringify(summary));
}

async function addToPendingIndex(kv: KVNamespace, jobId: string): Promise<void> {
  const raw = await kv.get(mergePendingIndexKey());
  const ids: string[] = raw ? (JSON.parse(raw) as string[]) : [];
  if (!ids.includes(jobId)) {
    ids.push(jobId);
    await kv.put(mergePendingIndexKey(), JSON.stringify(ids));
  }
}

async function removeFromPendingIndex(kv: KVNamespace, jobId: string): Promise<void> {
  const raw = await kv.get(mergePendingIndexKey());
  const ids: string[] = raw ? (JSON.parse(raw) as string[]) : [];
  await kv.put(mergePendingIndexKey(), JSON.stringify(ids.filter((id) => id !== jobId)));
}

export async function resolveTheater(kv: KVNamespace, gameId: string): Promise<string | undefined> {
  const lobby = await loadLobby(kv, gameId);
  return lobby.blue?.theater || lobby.red?.theater;
}

export async function findActiveJobForUpload(
  kv: KVNamespace,
  gameId: string,
  canonicalName: string,
): Promise<MergeJob | null> {
  const latestRaw = await kv.get(mergeLatestKey(gameId));
  if (!latestRaw) return null;
  const summary = JSON.parse(latestRaw) as MergeLatestSummary;
  if (summary.canonical_name !== canonicalName) return null;
  if (summary.status !== "pending" && summary.status !== "running") return null;
  return loadMergeJob(kv, summary.job_id);
}

export async function enqueueMergeJob(
  kv: KVNamespace,
  params: Omit<MergeJob, "id" | "status" | "requested_at">,
): Promise<MergeJob | null> {
  const existing = await findActiveJobForUpload(kv, params.game_id, params.canonical_name);
  if (existing) return existing;

  const job: MergeJob = {
    ...params,
    id: randomJobId(),
    status: "pending",
    requested_at: new Date().toISOString(),
  };
  await saveMergeJob(kv, job);
  await addToPendingIndex(kv, job.id);
  return job;
}

export async function listPendingJobs(kv: KVNamespace): Promise<MergeJob[]> {
  const raw = await kv.get(mergePendingIndexKey());
  const ids: string[] = raw ? (JSON.parse(raw) as string[]) : [];
  const jobs: MergeJob[] = [];
  for (const id of ids) {
    const job = await loadMergeJob(kv, id);
    if (job && job.status === "pending") jobs.push(job);
  }
  return jobs;
}

export async function claimMergeJob(kv: KVNamespace, id: string): Promise<MergeJob | null> {
  const job = await loadMergeJob(kv, id);
  if (!job || job.status !== "pending") return null;
  job.status = "running";
  job.started_at = new Date().toISOString();
  await saveMergeJob(kv, job);
  await removeFromPendingIndex(kv, id);
  return job;
}

export async function completeMergeJob(
  kv: KVNamespace,
  id: string,
  result: { ok: boolean; error?: string; deploy_url?: string },
): Promise<MergeJob | null> {
  const job = await loadMergeJob(kv, id);
  if (!job) return null;
  job.status = result.ok ? "complete" : "failed";
  job.completed_at = new Date().toISOString();
  job.error = result.error;
  job.deploy_url = result.deploy_url;
  if (result.ok) {
    job.board_refresh_hint = "Refresh NetworkLinks in Google Earth Pro to see the updated board.";
    await kv.put(
      boardRefreshKey(job.game_id),
      JSON.stringify({
        at: job.completed_at,
        canonical_name: job.canonical_name,
        job_id: job.id,
      } satisfies BoardRefreshNotice),
    );
  }
  await saveMergeJob(kv, job);
  return job;
}

export async function getLatestMergeSummary(kv: KVNamespace, gameId: string): Promise<MergeLatestSummary | null> {
  const raw = await kv.get(mergeLatestKey(gameId));
  if (!raw) return null;
  return JSON.parse(raw) as MergeLatestSummary;
}

export async function getBoardRefreshNotice(kv: KVNamespace, gameId: string): Promise<BoardRefreshNotice | null> {
  const raw = await kv.get(boardRefreshKey(gameId));
  if (!raw) return null;
  return JSON.parse(raw) as BoardRefreshNotice;
}

export function cellFromCanonicalName(name: string): "blue-cell" | "red-cell" | null {
  if (name.includes("BlueCell")) return "blue-cell";
  if (name.includes("RedCell")) return "red-cell";
  return null;
}

export function autoMergeEnabled(env: Env): boolean {
  const flag = (env as Record<string, string | undefined>).AUTO_MERGE_ON_UPLOAD;
  return flag !== "false" && flag !== "0";
}

export async function triggerMergeRunner(
  env: Env,
  job: MergeJob,
  portalOrigin: string,
): Promise<{ triggered: boolean; method?: string }> {
  const payload = {
    job_id: job.id,
    game_id: job.game_id,
    portal_origin: portalOrigin,
  };

  const webhook = (env as Record<string, string | undefined>).MERGE_RUNNER_WEBHOOK_URL;
  if (webhook) {
    try {
      await fetch(webhook, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return { triggered: true, method: "webhook" };
    } catch (err) {
      console.error("merge_webhook_failed", err);
    }
  }

  const token = (env as Record<string, string | undefined>).GITHUB_MERGE_DISPATCH_TOKEN;
  const repo = (env as Record<string, string | undefined>).GITHUB_REPO;
  if (token && repo) {
    const [owner, name] = repo.split("/");
    if (owner && name) {
      try {
        const res = await fetch(`https://api.github.com/repos/${owner}/${name}/dispatches`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
          },
          body: JSON.stringify({
            event_type: "merge-portal-turn",
            client_payload: payload,
          }),
        });
        if (res.ok) return { triggered: true, method: "github_dispatch" };
        console.error("merge_dispatch_failed", res.status, await res.text());
      } catch (err) {
        console.error("merge_dispatch_failed", err);
      }
    }
  }

  return { triggered: false };
}

export function mergeRunnerHint(env: Env): string {
  if ((env as Record<string, string | undefined>).MERGE_RUNNER_WEBHOOK_URL) {
    return "Merge runner webhook configured.";
  }
  if ((env as Record<string, string | undefined>).GITHUB_MERGE_DISPATCH_TOKEN) {
    return "GitHub merge runner configured — job queued for CI.";
  }
  return "No merge runner configured — run: python3 scripts/merge_runner_daemon.py";
}