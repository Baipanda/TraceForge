import axios from "axios";

const USER_KEY = "todo_user";

const http = axios.create({
  baseURL: "/api",
  timeout: 15000,
});

export function getCurrentUsername() {
  return (window.__todo_user || localStorage.getItem(USER_KEY) || "").trim();
}

export function setCurrentUsername(username) {
  const value = (username || "").trim();
  if (value) {
    localStorage.setItem(USER_KEY, value);
    window.__todo_user = value;
  } else {
    localStorage.removeItem(USER_KEY);
    window.__todo_user = "";
  }
}

http.interceptors.request.use((config) => {
  const username = getCurrentUsername();
  if (username) {
    config.headers = config.headers || {};
    config.headers["X-User"] = encodeURIComponent(username);
    config.headers["X-User-Encoded"] = "uri";
  }
  return config;
});

export { http };

export default {
  getStats() { return http.get("/stats"); },
  getPeople() { return http.get("/people"); },
  getProjects() { return http.get("/projects"); },
  getSubtrees() { return http.get("/subtrees"); },

  getTodos(params = {}) { return http.get("/todos", { params }); },
  getTodo(id) { return http.get(`/todos/${id}`); },
  updateChildWeights(id, data) { return http.put(`/todos/${id}/child-weights`, data); },
  getTodoProgress(id, params = {}) { return http.get(`/todos/${id}/progress`, { params }); },
  createTodoProgress(id, data) { return http.post(`/todos/${id}/progress`, data); },
  confirmTodoProgress(id, progressId) { return http.post(`/todos/${id}/progress/${progressId}/confirm`); },

  createTodo(data) {
    return http.post("/todos", data);
  },
  updateTodo(id, data) {
    return http.put(`/todos/${id}`, data);
  },
  deleteTodo(id) {
    return http.delete(`/todos/${id}`);
  },
};
