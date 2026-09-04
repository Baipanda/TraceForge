const MENTOR_KEY = "project-admin-mentor";

export function getMentor() {
  return localStorage.getItem(MENTOR_KEY) || "";
}

export function setMentor(name) {
  localStorage.setItem(MENTOR_KEY, name);
}

export function clearMentor() {
  localStorage.removeItem(MENTOR_KEY);
}

async function request(path, { method = "GET", body, mentor } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const m = mentor ?? getMentor();
  if (m) headers["X-Mentor"] = m;

  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || res.statusText || "request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  mentors: () => request("/api/mentors"),
  listProjects: (params = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.set(k, v);
    });
    const qs = q.toString();
    return request(`/api/projects${qs ? `?${qs}` : ""}`);
  },
  getProject: (id) => request(`/api/projects/${encodeURIComponent(id)}`),
  createProject: (body) => request("/api/projects", { method: "POST", body }),
  updateProject: (id, body) =>
    request(`/api/projects/${encodeURIComponent(id)}`, { method: "PUT", body }),
  archiveProject: (id) =>
    request(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" }),
  addMember: (id, body) =>
    request(`/api/projects/${encodeURIComponent(id)}/members`, { method: "POST", body }),
  removeMember: (id, memberId) =>
    request(`/api/projects/${encodeURIComponent(id)}/members/${memberId}`, {
      method: "DELETE",
    }),
  listReports: (id) => request(`/api/projects/${encodeURIComponent(id)}/reports`),
  getReport: (reportId) => request(`/api/reports/${reportId}`),
  createReport: (body) => request("/api/reports", { method: "POST", body }),
};
