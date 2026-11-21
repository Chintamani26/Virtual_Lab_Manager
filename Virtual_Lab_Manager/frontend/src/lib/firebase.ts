/**
 * Firebase (Auth + Firestore real-time) — enabled when NEXT_PUBLIC_FIREBASE_API_KEY is set at build time.
 *
 * - Auth: demo / real accounts sign in with Firebase; the API receives the Firebase ID token as Bearer.
 * - Firestore: the browser only *reads* `exam_live` (see firebase/firestore.rules). Every listener here is a
 *   "something changed — refresh now" signal on top of the existing polling, and degrades silently to
 *   polling if the listener fails (permissions, offline, misconfiguration).
 *
 * The SDK is loaded lazily so local (Firebase-off) builds and pages that never use it pay nothing.
 */
import type { FirebaseApp } from "firebase/app";
import type { Auth } from "firebase/auth";
import type { Firestore } from "firebase/firestore";

// NEXT_PUBLIC_* must be referenced literally so Next.js inlines them at build time.
const config = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "",
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "",
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "",
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ?? "",
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || undefined,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || undefined,
};

export const firebaseEnabled = Boolean(config.apiKey && config.projectId && config.appId);
export const firebaseProjectId = config.projectId || null;

let appPromise: Promise<FirebaseApp> | null = null;
let authPromise: Promise<Auth> | null = null;
let dbPromise: Promise<Firestore> | null = null;

function app(): Promise<FirebaseApp> {
  if (!firebaseEnabled) return Promise.reject(new Error("Firebase is not configured"));
  appPromise ??= import("firebase/app").then(({ getApps, initializeApp }) => getApps()[0] ?? initializeApp(config));
  return appPromise;
}

function auth(): Promise<Auth> {
  authPromise ??= Promise.all([app(), import("firebase/auth")]).then(async ([a, m]) => {
    const instance = m.getAuth(a);
    await instance.authStateReady(); // restore the persisted sign-in before the first API call
    return instance;
  });
  return authPromise;
}

function db(): Promise<Firestore> {
  dbPromise ??= Promise.all([app(), import("firebase/firestore")]).then(([a, m]) => m.getFirestore(a));
  return dbPromise;
}

// ------------------------------------------------------------------ auth
const FIREBASE_ERRORS: Record<string, string> = {
  "auth/invalid-credential": "Wrong email or password.",
  "auth/invalid-login-credentials": "Wrong email or password.",
  "auth/user-not-found": "No account with that email.",
  "auth/wrong-password": "Wrong email or password.",
  "auth/user-disabled": "This account has been disabled.",
  "auth/too-many-requests": "Too many attempts — wait a minute and try again.",
  "auth/network-request-failed": "Cannot reach Firebase — check your connection.",
  "auth/operation-not-allowed": "Email/password sign-in is not enabled for this Firebase project.",
};

export function firebaseErrorMessage(err: unknown): string {
  const code = typeof err === "object" && err && "code" in err ? String((err as { code: unknown }).code) : "";
  return FIREBASE_ERRORS[code] ?? (err instanceof Error ? err.message : "Sign-in failed.");
}

/** Signs in with Firebase Auth and returns a fresh ID token. Throws Error with a human message. */
export async function firebaseSignIn(email: string, password: string): Promise<string> {
  const [a, m] = await Promise.all([auth(), import("firebase/auth")]);
  try {
    const cred = await m.signInWithEmailAndPassword(a, email, password);
    return await cred.user.getIdToken(true); // force: pick up custom claims set by the seed / admin
  } catch (err) {
    throw new Error(firebaseErrorMessage(err));
  }
}

/** Current user's ID token (auto-refreshed by the SDK when close to expiry); null when signed out. */
export async function firebaseIdToken(): Promise<string | null> {
  if (!firebaseEnabled) return null;
  try {
    const a = await auth();
    return a.currentUser ? await a.currentUser.getIdToken() : null;
  } catch {
    return null;
  }
}

export async function firebaseSignOut(): Promise<void> {
  if (!firebaseEnabled) return;
  try {
    const [a, m] = await Promise.all([auth(), import("firebase/auth")]);
    await m.signOut(a);
  } catch {
    /* already signed out */
  }
}

/** Keeps a synchronous copy of the latest ID token fresh (used for keepalive requests during page unload). */
export function watchIdToken(onToken: (token: string | null) => void): () => void {
  if (!firebaseEnabled) return () => {};
  let unsub: (() => void) | null = null;
  let cancelled = false;
  Promise.all([auth(), import("firebase/auth")])
    .then(([a, m]) => {
      if (cancelled) return;
      unsub = m.onIdTokenChanged(a, async (u) => onToken(u ? await u.getIdToken() : null));
    })
    .catch((err) => {
      if (process.env.NODE_ENV !== "production") console.warn("[firebase] token watcher unavailable:", err);
    });
  return () => {
    cancelled = true;
    unsub?.();
  };
}

// ------------------------------------------------------------------ exam_live (real-time, read-only)
export type ExamLiveStatus = "active" | "locked" | "submitted";

export interface ExamLiveDoc {
  practical_id: string;
  student_id: string;
  student_name?: string;
  status: ExamLiveStatus;
  lock_reason: string | null;
  violations: number;
}

type Unsubscribe = () => void;

/**
 * Wraps an async-created Firestore listener so callers get a synchronous unsubscribe. On a listener
 * error (e.g. permission-denied when claims are missing) it unsubscribes and calls `onError` once —
 * callers keep polling, so nothing breaks.
 */
function listen(
  start: (fs: typeof import("firebase/firestore"), d: Firestore, onErr: (e: unknown) => void) => Unsubscribe,
  onError?: (e: unknown) => void,
): Unsubscribe {
  if (!firebaseEnabled) return () => {};
  let unsub: Unsubscribe | null = null;
  let stopped = false;
  const fail = (e: unknown) => {
    if (stopped) return;
    stopped = true;
    unsub?.();
    if (process.env.NODE_ENV !== "production") console.warn("[firebase] live updates unavailable, polling instead:", e);
    onError?.(e);
  };
  Promise.all([import("firebase/firestore"), db(), auth()])
    .then(([fs, d, a]) => {
      if (stopped || !a.currentUser) return; // not signed in with Firebase → stay on polling
      unsub = start(fs, d, fail);
    })
    .catch(fail);
  return () => {
    stopped = true;
    unsub?.();
  };
}

function toLive(id: string, data: Record<string, unknown>): ExamLiveDoc {
  return {
    practical_id: String(data.practical_id ?? id.split("__")[0]),
    student_id: String(data.student_id ?? id.split("__")[1]),
    student_name: typeof data.student_name === "string" ? data.student_name : undefined,
    status: (data.status as ExamLiveStatus) ?? "active",
    lock_reason: (data.lock_reason as string | null) ?? null,
    violations: Number(data.violations ?? 0),
  };
}

/** Student: their own exam status. `null` until the exam is first started. */
export function subscribeExamLive(
  practicalId: string,
  studentId: string,
  onChange: (doc: ExamLiveDoc | null) => void,
  onError?: (e: unknown) => void,
): Unsubscribe {
  return listen(
    (fs, d, onErr) =>
      fs.onSnapshot(
        fs.doc(d, "exam_live", `${practicalId}__${studentId}`),
        (snap) => onChange(snap.exists() ? toLive(snap.id, snap.data()) : null),
        onErr,
      ),
    onError,
  );
}

/** Staff: every student's exam status for one practical (rules require the staff_ids constraint). */
export function subscribePracticalExams(
  practicalId: string,
  staffId: string,
  onChange: (docs: ExamLiveDoc[]) => void,
  onError?: (e: unknown) => void,
): Unsubscribe {
  return listen(
    (fs, d, onErr) =>
      fs.onSnapshot(
        fs.query(
          fs.collection(d, "exam_live"),
          fs.where("practical_id", "==", practicalId),
          fs.where("staff_ids", "array-contains", staffId),
        ),
        (snap) => onChange(snap.docs.map((x) => toLive(x.id, x.data()))),
        onErr,
      ),
    onError,
  );
}

/** Staff: all currently locked exams they supervise (alerts bell). */
export function subscribeLockedExams(
  staffId: string,
  onChange: (docs: ExamLiveDoc[]) => void,
  onError?: (e: unknown) => void,
): Unsubscribe {
  return listen(
    (fs, d, onErr) =>
      fs.onSnapshot(
        fs.query(
          fs.collection(d, "exam_live"),
          fs.where("staff_ids", "array-contains", staffId),
          fs.where("status", "==", "locked"),
        ),
        (snap) => onChange(snap.docs.map((x) => toLive(x.id, x.data()))),
        onErr,
      ),
    onError,
  );
}
