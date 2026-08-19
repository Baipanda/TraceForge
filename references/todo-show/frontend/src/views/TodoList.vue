<template>
  <div>
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
      <div class="d-flex align-items-baseline gap-2">
        <h3 class="mb-0"><i class="bi bi-list-ul me-2"></i>Todo 列表</h3>
        <span class="text-muted small">共 {{ total }} 条</span>
      </div>
      <div class="d-flex align-items-center gap-2">
        <div class="btn-group btn-group-sm" role="group" aria-label="列表展示方式">
          <button
            type="button"
            class="btn"
            :class="!treeMode ? 'btn-secondary' : 'btn-outline-secondary'"
            title="普通列表"
            @click="switchView(false)"
          >
            <i class="bi bi-list-ul me-1"></i>列表
          </button>
          <button
            type="button"
            class="btn"
            :class="treeMode ? 'btn-secondary' : 'btn-outline-secondary'"
            title="按父子关系展示"
            @click="switchView(true)"
          >
            <i class="bi bi-diagram-3 me-1"></i>树形
          </button>
        </div>
        <div class="dropdown">
          <button
            class="btn btn-sm btn-outline-secondary"
            type="button"
            data-bs-toggle="dropdown"
            data-bs-auto-close="outside"
            title="选择表格列"
          >
            <i class="bi bi-layout-three-columns me-1"></i>列设置
          </button>
          <div class="dropdown-menu dropdown-menu-end p-3 column-menu">
            <div v-for="column in optionalColumnOptions" :key="column.key" class="form-check mb-2">
              <input
                :id="`column-${column.key}`"
                class="form-check-input"
                type="checkbox"
                v-model="optionalColumns[column.key]"
              />
              <label class="form-check-label small" :for="`column-${column.key}`">{{ column.label }}</label>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="successMessage" class="alert alert-success py-2 mb-3">
      <i class="bi bi-check-circle me-2"></i>{{ successMessage }}
    </div>

    <div class="d-flex flex-wrap gap-2 mb-3">
      <button
        v-for="s in statsItems"
        :key="s.label"
        type="button"
        class="btn btn-sm"
        :class="statusFilter === s.filter ? s.activeClass : 'btn-outline-secondary'"
        @click="toggleStatus(s.filter)"
      >
        {{ s.label }} {{ s.count }}
      </button>
    </div>

    <div class="sync-quick-bar d-flex flex-wrap align-items-center gap-2 mb-3">
      <span class="small fw-semibold text-muted me-1">同步安排</span>
      <button
        v-for="item in syncQuickItems"
        :key="item.filter || 'all'"
        type="button"
        class="btn btn-sm"
        :class="syncDueFilter === item.filter ? item.activeClass : 'btn-outline-secondary'"
        @click="applySyncDueFilter(item.filter)"
      >
        {{ item.label }}<span v-if="item.count !== null" class="ms-1">{{ item.count }}</span>
      </button>
    </div>

    <div class="filter-bar mb-3">
      <div class="row g-2 align-items-end">
        <div class="col-auto">
          <label class="form-label small mb-1">工作状态</label>
          <select class="form-select form-select-sm" v-model="statusFilter" @change="onStatusFilterChange">
            <option value="">全部</option>
            <option value="pending">待处理</option>
            <option value="completed">已完成</option>
            <option value="cancelled">已取消</option>
            <option value="expired">已过期</option>
          </select>
        </div>
        <div class="col-auto">
          <label class="form-label small mb-1">事项类型</label>
          <select class="form-select form-select-sm" v-model="bugFilter" @change="search">
            <option value="">全部</option>
            <option value="true">Bug（{{ bugCount }}）</option>
            <option value="false">普通 Todo</option>
          </select>
        </div>
        <div class="col-auto">
          <label class="form-label small mb-1">优先级</label>
          <select class="form-select form-select-sm" v-model="priorityFilter" @change="search">
            <option value="">全部</option>
            <option value="high">高</option>
            <option value="normal">普通</option>
            <option value="low">低</option>
          </select>
        </div>
        <div class="col-auto">
          <label class="form-label small mb-1">分类</label>
          <select class="form-select form-select-sm category-filter" v-model="subtreeFilter" @change="search">
            <option value="">全部</option>
            <option v-for="t in subtreeOptions" :key="t.id" :value="t.id">
              {{ "─".repeat(t.level - 1) }} {{ t.name }}
            </option>
          </select>
        </div>
        <div class="col-auto parent-filter">
          <label class="form-label small mb-1">父 Todo</label>
          <div class="position-relative mb-1">
            <input
              class="form-control form-control-sm"
              v-model="parentSearch"
              placeholder="输入标题搜索"
              @keyup.enter="selectFirstParentOption"
              @keydown.esc="parentSearch = ''"
            />
            <span v-if="parentOptionsLoading" class="spinner-border spinner-border-sm parent-search-spinner"></span>
            <div v-if="parentSearch" class="parent-suggestions shadow-sm">
              <button
                v-for="todo in parentOptions"
                :key="todo.id"
                v-show="!parentOptionsLoading"
                type="button"
                class="parent-suggestion"
                :title="todo.title"
                @mousedown.prevent="chooseParent(todo)"
              >
                {{ todo.title }}
              </button>
              <div v-if="!parentOptionsLoading && parentOptions.length === 0" class="parent-suggestion-empty">
                未找到匹配的父 Todo
              </div>
            </div>
          </div>
          <select class="form-select form-select-sm" v-model="parentFilter" @change="onParentFilterChange">
            <option value="">全部</option>
            <option v-for="t in parentOptions" :key="t.id" :value="t.id">
              {{ truncate(t.title, 28) }}
            </option>
          </select>
        </div>
        <div class="col-auto">
          <label class="form-label small mb-1">主力人员</label>
          <select class="form-select form-select-sm people-filter" v-model="mainForceFilter" @change="onRoleFilterChange">
            <option value="">全部</option>
            <option v-for="p in peopleOptions" :key="p.id" :value="String(p.id)">
              {{ p.canonical_name }}
            </option>
          </select>
        </div>
        <div class="col-auto">
          <label class="form-label small mb-1">流程管理人员</label>
          <select class="form-select form-select-sm people-filter" v-model="processManagerFilter" @change="onRoleFilterChange">
            <option value="">全部</option>
            <option v-for="p in peopleOptions" :key="p.id" :value="String(p.id)">
              {{ p.canonical_name }}
            </option>
          </select>
        </div>
        <div class="col-auto">
          <label class="form-label small mb-1">人员范围</label>
          <div class="form-check form-switch mine-switch mb-0">
            <input
              id="mine-only"
              class="form-check-input"
              type="checkbox"
              v-model="mineOnly"
              :disabled="!currentUserId"
              @change="onMineOnlyChange"
            />
            <label class="form-check-label small" for="mine-only">只看与我相关</label>
          </div>
        </div>
        <div class="col-auto">
          <label class="form-label small mb-1">排序</label>
          <select class="form-select form-select-sm" v-model="sortBy" @change="search">
            <option value="created_at_desc">创建时间 ↓</option>
            <option value="created_at_asc">创建时间 ↑</option>
            <option value="updated_at_desc">更新时间 ↓</option>
            <option value="priority_desc">优先级 ↓</option>
            <option value="next_sync_asc">下次同步时间 ↑</option>
          </select>
        </div>
        <div class="col search-filter">
          <label class="form-label small mb-1">搜索</label>
          <div class="input-group input-group-sm">
            <input class="form-control" v-model="searchQ" placeholder="搜索标题" @keyup.enter="search" />
            <button class="btn btn-outline-secondary" type="button" title="搜索" @click="search">
              <i class="bi bi-search"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="table-responsive todo-table-wrap">
      <table class="table table-hover align-middle mb-0 todo-table" :class="{ 'tree-table': treeMode }">
        <thead>
          <tr>
            <th class="title-column">标题</th>
            <th class="category-column">分类</th>
            <th class="priority-column">优先级</th>
            <th class="people-column">主力人员</th>
            <th class="people-column">流程管理人员</th>
            <th class="sync-column">同步状态</th>
            <th class="work-status-column">工作状态</th>
            <th class="hint-column">状态提示</th>
            <th v-if="optionalColumns.next_sync_at" class="date-column">下一次同步时间</th>
            <th v-if="optionalColumns.track_frequency" class="frequency-column">同步频率</th>
            <th v-if="optionalColumns.created_at" class="date-column">创建时间</th>
            <th v-if="optionalColumns.parent_todo" class="parent-column">父 Todo</th>
            <th class="action-column">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="t in displayTodos"
            :key="t.id"
            :data-todo-id="t.id"
            :class="{ 'todo-return-highlight': highlightedTodoId === t.id }"
          >
            <td>
              <div class="tree-title" :style="treeTitleStyle(t)">
                <button
                  v-if="treeMode && t._hasTreeChildren"
                  type="button"
                  class="tree-toggle border"
                  :title="isTodoExpanded(t.id) ? '收起子 Todo' : '展开子 Todo'"
                  :aria-label="isTodoExpanded(t.id) ? '收起子 Todo' : '展开子 Todo'"
                  @click="toggleTodoTree(t.id)"
                >
                  <i class="bi" :class="isTodoExpanded(t.id) ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                </button>
                <span v-else-if="treeMode" class="tree-toggle-placeholder"></span>
                <router-link
                  class="todo-title"
                  :to="`/todos/${t.id}`"
                  :title="t.title"
                  @click="rememberTodoPosition(t.id)"
                >
                  <span v-if="t.is_bug" class="badge text-bg-danger bug-badge">BUG</span>
                  {{ t.title }}
                </router-link>
              </div>
            </td>
            <td><span class="cell-text" :title="t.subtree_name">{{ t.subtree_name }}</span></td>
            <td><span class="badge" :class="priorityClass(t.priority)">{{ priorityLabel(t.priority) }}</span></td>
            <td><span class="cell-text" :title="peopleText(t.main_force_names)">{{ peopleText(t.main_force_names) }}</span></td>
            <td><span class="cell-text" :title="peopleText(t.process_manager_names)">{{ peopleText(t.process_manager_names) }}</span></td>
            <td>
              <div class="d-flex align-items-center sync-state">
                <span
                  class="badge"
                  :class="syncStatusClass(t.status_meta?.tone)"
                  :title="t.status_meta?.hint"
                >{{ t.status_meta?.label || "—" }}</span>
                <button
                  type="button"
                  class="btn btn-sm btn-link sync-button"
                  title="查看最近同步历史"
                  @click="openSyncHistory(t)"
                >
                  <i class="bi bi-clock-history"></i>
                </button>
                <button
                  type="button"
                  class="btn btn-sm btn-link sync-button"
                  :disabled="!canFillProgress(t)"
                  :title="progressButtonTitle(t)"
                  @click="openProgress(t)"
                >
                  <i class="bi bi-pencil-square"></i>
                </button>
                <button
                  type="button"
                  class="btn btn-sm btn-link sync-button confirm-button"
                  :disabled="!canConfirmProgress(t) || confirmSavingId === t.id"
                  :title="canConfirmProgress(t) ? '确认本次同步' : '请先填写进展'"
                  @click="confirmProgress(t)"
                >
                  <span v-if="confirmSavingId === t.id" class="spinner-border spinner-border-sm"></span>
                  <i v-else class="bi bi-check-circle"></i>
                </button>
              </div>
            </td>
            <td>
              <span
                class="badge"
                :class="statusClass(t.status)"
                :title="t.auto_completed_by_children ? '所有子 Todo 均已结束，系统自动完成' : ''"
              >{{ statusLabel(t.status) }}</span>
            </td>
            <td><span class="status-hint" :title="t.progress_prompt">{{ t.progress_prompt || "—" }}</span></td>
            <td v-if="optionalColumns.next_sync_at"><small>{{ formatDate(t.next_sync_at) || "—" }}</small></td>
            <td v-if="optionalColumns.track_frequency"><small>{{ t.track_frequency_label || "—" }}</small></td>
            <td v-if="optionalColumns.created_at"><small>{{ formatDate(t.created_at) }}</small></td>
            <td v-if="optionalColumns.parent_todo">
              <router-link v-if="t.parent_title" class="cell-text" :to="`/todos/${t.parent_id}`" :title="t.parent_title">
                {{ t.parent_title }}
              </router-link>
              <span v-else-if="t.parent_id" class="text-muted small">已删除</span>
              <span v-else class="text-muted">—</span>
            </td>
            <td class="action-cell">
              <button
                v-if="t.status === 'pending'"
                type="button"
                class="btn btn-sm btn-outline-success icon-button"
                title="标记为完成"
                @click="completeTodo(t.id)"
              >
                <i class="bi bi-check-lg"></i>
              </button>
            </td>
          </tr>
          <tr v-if="todos.length === 0 && !loading">
            <td :colspan="visibleColumnCount" class="text-center text-muted py-5">暂无数据</td>
          </tr>
          <tr v-if="loading">
            <td :colspan="visibleColumnCount" class="text-center py-5">
              <div class="spinner-border spinner-border-sm text-secondary"></div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="error" class="alert alert-danger mt-3 d-flex align-items-center">
      <i class="bi bi-exclamation-triangle me-2"></i>{{ error }}
      <button class="btn btn-sm btn-outline-danger ms-auto" @click="fetchTodos">重试</button>
    </div>

    <nav class="mt-3" v-if="!treeMode && pages > 1">
      <ul class="pagination pagination-sm justify-content-center">
        <li class="page-item" :class="{ disabled: page <= 1 }">
          <a class="page-link" href="#" @click.prevent="goPage(page - 1)">&laquo;</a>
        </li>
        <li class="page-item" v-for="p in visiblePages" :key="p" :class="{ active: p === page }">
          <a class="page-link" href="#" @click.prevent="goPage(p)">{{ p }}</a>
        </li>
        <li class="page-item" :class="{ disabled: page >= pages }">
          <a class="page-link" href="#" @click.prevent="goPage(page + 1)">&raquo;</a>
        </li>
      </ul>
    </nav>

    <template v-if="progressTodo">
      <div class="modal d-block" tabindex="-1" role="dialog" aria-modal="true">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <div>
                <h5 class="modal-title">同步进展</h5>
                <div class="text-muted small text-truncate modal-todo-title">{{ progressTodo.title }}</div>
              </div>
              <button type="button" class="btn-close" aria-label="关闭" @click="closeProgress"></button>
            </div>
            <div class="modal-body">
              <div class="progress-prompt mb-3">
                <div class="small fw-semibold mb-1">填写提示</div>
                <div class="small">{{ progressTodo.progress_prompt }}</div>
              </div>
              <label class="form-label" for="progress-content">同步进展</label>
              <textarea
                id="progress-content"
                ref="progressInput"
                class="form-control"
                v-model="progressContent"
                rows="7"
                maxlength="5000"
                placeholder="请输入本次进展"
              ></textarea>
              <div class="d-flex justify-content-between mt-1">
                <small v-if="progressError" class="text-danger">{{ progressError }}</small>
                <small v-else class="text-muted">提交后将保存在进展历史中</small>
                <small class="text-muted">{{ progressContent.length }}/5000</small>
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-primary" :disabled="progressSaving || !progressContent.trim()" @click="submitProgress">
                <span v-if="progressSaving" class="spinner-border spinner-border-sm me-1"></span>
                保存进展
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-backdrop show"></div>
    </template>

    <template v-if="historyTodo">
      <div class="modal d-block" tabindex="-1" role="dialog" aria-modal="true">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <div class="overflow-hidden">
                <h5 class="modal-title">同步历史</h5>
                <div class="text-muted small text-truncate modal-todo-title">{{ historyTodo.title }}</div>
              </div>
              <button type="button" class="btn-close" aria-label="关闭" @click="closeSyncHistory"></button>
            </div>
            <div class="modal-body">
              <div v-if="historyLoading" class="text-center py-4">
                <div class="spinner-border spinner-border-sm" role="status"></div>
              </div>
              <div v-else-if="historyError" class="alert alert-danger mb-0">{{ historyError }}</div>
              <div v-else-if="historyRecords.length" class="list-group list-group-flush sync-history-list">
                <div
                  v-for="entry in historyRecords"
                  :key="entry.id"
                  class="list-group-item px-0"
                  :class="{ 'sync-history-revoked': entry.revoked_at }"
                >
                  <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
                    <strong class="small">{{ entry.recorded_by_name }}</strong>
                    <small class="text-muted">{{ formatDate(entry.recorded_at) }}</small>
                    <span v-if="entry.source === 'children_rollup'" class="badge text-bg-info">系统汇总</span>
                    <span v-if="entry.revoked_at" class="badge text-bg-secondary">已失效</span>
                    <span v-else-if="entry.confirmed_at" class="badge text-bg-success">已确认</span>
                    <span v-else class="badge text-bg-warning">待确认</span>
                  </div>
                  <div class="small sync-history-content">{{ entry.content }}</div>
                  <small v-if="entry.confirmed_at && !entry.revoked_at" class="text-muted d-block mt-2">
                    {{ entry.confirmed_by_name }} 于 {{ formatDate(entry.confirmed_at) }} 确认同步
                  </small>
                  <small v-else-if="entry.revoked_at" class="text-muted d-block mt-2">
                    此次系统汇总于 {{ formatDate(entry.revoked_at) }} 失效
                  </small>
                </div>
              </div>
              <div v-else class="text-muted text-center py-4">暂无同步历史</div>
              <div v-if="historyTotal > 3" class="text-muted small text-end mt-2">
                仅显示最近 3 条
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-backdrop show"></div>
    </template>
  </div>
</template>

<script>
import api, { getCurrentUsername } from "../api/index.js";

const COLUMN_PREF_KEY = "todo_list_optional_columns";
const LIST_NAVIGATION_STATE_KEY = "todo_list_navigation_state";
const LIST_NAVIGATION_STATE_MAX_AGE = 30 * 60 * 1000;
const DEFAULT_OPTIONAL_COLUMNS = {
  next_sync_at: false,
  track_frequency: false,
  created_at: false,
  parent_todo: false,
};

function loadColumnPreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem(COLUMN_PREF_KEY) || "{}");
    return Object.fromEntries(
      Object.keys(DEFAULT_OPTIONAL_COLUMNS).map(key => [key, Boolean(saved[key])])
    );
  } catch {
    return { ...DEFAULT_OPTIONAL_COLUMNS };
  }
}

export default {
  name: "TodoList",
  data() {
    return {
      todos: [],
      total: 0,
      page: 1,
      size: 30,
      pages: 0,
      loading: false,
      treeMode: true,
      expandedTodoIds: [],
      highlightedTodoId: "",
      returnFocusTodoId: "",
      returnScrollY: 0,
      highlightTimer: null,
      statusFilter: "",
      bugFilter: "",
      bugCount: 0,
      syncDueFilter: "",
      priorityFilter: "",
      subtreeFilter: "",
      parentFilter: "",
      mainForceFilter: "",
      processManagerFilter: "",
      mineOnly: true,
      currentUserId: "",
      sortBy: "created_at_desc",
      searchQ: "",
      statsItems: [
        { label: "全部", count: 0, filter: "", activeClass: "btn-secondary" },
        { label: "待处理", count: 0, filter: "pending", activeClass: "btn-warning" },
        { label: "已完成", count: 0, filter: "completed", activeClass: "btn-success" },
        { label: "已取消", count: 0, filter: "cancelled", activeClass: "btn-danger" },
      ],
      syncQuickItems: [
        { label: "全部", count: null, filter: "", activeClass: "btn-secondary" },
        { label: "当前需同步", count: 0, filter: "needs_today", activeClass: "btn-primary" },
        { label: "今日已填写", count: 0, filter: "filled_today", activeClass: "btn-info" },
        { label: "今日已同步", count: 0, filter: "synced_today", activeClass: "btn-success" },
        { label: "已逾期", count: 0, filter: "overdue", activeClass: "btn-danger" },
        { label: "今日到期", count: 0, filter: "due_today", activeClass: "btn-warning" },
        { label: "未来 7 天", count: 0, filter: "next_7_days", activeClass: "btn-info" },
        { label: "未设置频率", count: 0, filter: "not_configured", activeClass: "btn-secondary" },
      ],
      subtreeOptions: [],
      parentOptions: [],
      peopleOptions: [],
      parentSearch: "",
      parentSearchTimer: null,
      parentOptionsLoading: false,
      parentOptionsRequestId: 0,
      error: "",
      successMessage: "",
      successTimer: null,
      optionalColumns: loadColumnPreferences(),
      optionalColumnOptions: [
        { key: "next_sync_at", label: "下一次同步时间" },
        { key: "track_frequency", label: "同步频率" },
        { key: "created_at", label: "创建时间" },
        { key: "parent_todo", label: "父 Todo" },
      ],
      progressTodo: null,
      progressContent: "",
      progressError: "",
      progressSaving: false,
      confirmSavingId: "",
      historyTodo: null,
      historyRecords: [],
      historyTotal: 0,
      historyLoading: false,
      historyError: "",
    };
  },
  computed: {
    displayTodos() {
      if (!this.treeMode) {
        return this.todos.map(todo => ({ ...todo, _treeDepth: 0, _hasTreeChildren: false }));
      }

      const nodes = new Map(
        this.todos.map(todo => [todo.id, { ...todo, _treeChildren: [] }])
      );
      const roots = [];
      nodes.forEach(node => {
        const parent = node.parent_id ? nodes.get(node.parent_id) : null;
        if (parent) parent._treeChildren.push(node);
        else roots.push(node);
      });

      const visible = [];
      const appendNode = (node, depth) => {
        const hasChildren = node._treeChildren.length > 0;
        visible.push({ ...node, _treeDepth: depth, _hasTreeChildren: hasChildren });
        if (hasChildren && this.expandedTodoIds.includes(node.id)) {
          node._treeChildren.forEach(child => appendNode(child, depth + 1));
        }
      };
      roots.forEach(root => appendNode(root, 0));
      return visible;
    },
    visiblePages() {
      const result = [];
      const start = Math.max(1, this.page - 2);
      const end = Math.min(this.pages, this.page + 2);
      for (let value = start; value <= end; value += 1) result.push(value);
      return result;
    },
    visibleColumnCount() {
      return 9 + Object.values(this.optionalColumns).filter(Boolean).length;
    },
  },
  watch: {
    parentSearch() {
      clearTimeout(this.parentSearchTimer);
      this.parentSearchTimer = setTimeout(() => this.loadParentOptions(), 300);
    },
    optionalColumns: {
      deep: true,
      handler(value) {
        localStorage.setItem(COLUMN_PREF_KEY, JSON.stringify(value));
      },
    },
  },
  async mounted() {
    this.loadFromQuery();
    this.restoreNavigationState();
    await Promise.all([this.loadStats(), this.loadSubtrees(), this.loadPeople(), this.loadParentOptions()]);
    await this.ensureSelectedParentOption();
    await this.fetchTodos();
    await this.$nextTick();
    this.restoreNavigationPosition();
  },
  beforeUnmount() {
    clearTimeout(this.parentSearchTimer);
    clearTimeout(this.successTimer);
    clearTimeout(this.highlightTimer);
  },
  methods: {
    async loadStats() {
      try {
        const { data } = await api.getStats();
        this.statsItems[0].count = data.total;
        this.bugCount = data.bugs || 0;
        this.statsItems[1].count = data.pending;
        this.statsItems[2].count = data.completed;
        this.statsItems[3].count = data.cancelled;
        const counts = {
          needs_today: data.sync_needs_today,
          filled_today: data.sync_filled_today,
          synced_today: data.sync_synced_today,
          overdue: data.sync_overdue,
          due_today: data.sync_due_today,
          next_7_days: data.sync_next_7_days,
          not_configured: data.sync_not_configured,
        };
        this.syncQuickItems.forEach(item => {
          if (item.filter) item.count = counts[item.filter] ?? 0;
        });
      } catch (error) {
        console.error(error);
      }
    },
    async loadSubtrees() {
      try {
        this.subtreeOptions = [];
        this.flattenSubtrees((await api.getSubtrees()).data);
      } catch (error) {
        console.error(error);
      }
    },
    async loadPeople() {
      try {
        this.peopleOptions = (await api.getPeople()).data;
        const username = getCurrentUsername();
        const currentUser = this.peopleOptions.find(person => person.canonical_name === username);
        this.currentUserId = currentUser ? String(currentUser.id) : "";
        if (!this.currentUserId) this.mineOnly = false;
      } catch (error) {
        console.error(error);
      }
    },
    async loadParentOptions() {
      const requestId = ++this.parentOptionsRequestId;
      this.parentOptionsLoading = true;
      try {
        const { data } = await api.getTodos({
          size: 200,
          sort: "updated_at_desc",
          parents_only: true,
          q: this.parentSearch || undefined,
        });
        if (requestId !== this.parentOptionsRequestId) return;
        this.parentOptions = this.mergeSelectedParentOption(data.items);
      } catch (error) {
        if (requestId === this.parentOptionsRequestId) console.error(error);
      } finally {
        if (requestId === this.parentOptionsRequestId) this.parentOptionsLoading = false;
      }
    },
    mergeSelectedParentOption(items) {
      if (this.parentSearch || !this.parentFilter) return items;
      const selected = this.parentOptions.find(todo => todo.id === this.parentFilter);
      if (!selected || items.some(todo => todo.id === selected.id)) return items;
      return [selected, ...items];
    },
    async ensureSelectedParentOption() {
      if (!this.parentFilter || this.parentOptions.some(todo => todo.id === this.parentFilter)) return;
      try {
        const { data } = await api.getTodo(this.parentFilter);
        this.parentOptions.unshift({ id: data.id, title: data.title });
      } catch (error) {
        console.error(error);
      }
    },
    selectFirstParentOption() {
      if (!this.parentSearch) {
        this.parentFilter = "";
      } else if (this.parentOptions.length) {
        this.chooseParent(this.parentOptions[0]);
        return;
      } else {
        return;
      }
      this.search();
    },
    chooseParent(todo) {
      this.parentFilter = todo.id;
      this.parentOptions = [todo, ...this.parentOptions.filter(item => item.id !== todo.id)];
      this.parentSearch = "";
      this.search();
    },
    onParentFilterChange() {
      this.parentSearch = "";
      this.search();
    },
    flattenSubtrees(nodes) {
      for (const node of nodes) {
        this.subtreeOptions.push(node);
        if (node.children?.length) this.flattenSubtrees(node.children);
      }
    },
    loadFromQuery() {
      const query = this.$route.query;
      this.statusFilter = query.status || "";
      this.bugFilter = ["true", "false"].includes(query.is_bug) ? query.is_bug : "";
      this.syncDueFilter = query.sync_due || "";
      if (this.syncDueFilter) this.statusFilter = "pending";
      this.priorityFilter = ["high", "normal", "low"].includes(query.priority)
        ? query.priority
        : "";
      this.subtreeFilter = query.subtree_id || "";
      this.parentFilter = query.parent_id || "";
      this.mainForceFilter = query.main_force_id ? String(query.main_force_id) : "";
      this.processManagerFilter = query.process_manager_id ? String(query.process_manager_id) : "";
      this.mineOnly = query.scope !== "all" && !this.mainForceFilter && !this.processManagerFilter;
      this.treeMode = query.view !== "list";
      this.searchQ = query.q || "";
      this.page = query.page ? Number.parseInt(query.page, 10) || 1 : 1;
      this.sortBy = query.sort || "created_at_desc";
    },
    syncQuery() {
      const query = {};
      if (this.statusFilter) query.status = this.statusFilter;
      if (this.bugFilter) query.is_bug = this.bugFilter;
      if (this.syncDueFilter) query.sync_due = this.syncDueFilter;
      if (this.priorityFilter) query.priority = this.priorityFilter;
      if (this.subtreeFilter) query.subtree_id = this.subtreeFilter;
      if (this.parentFilter) query.parent_id = this.parentFilter;
      if (this.mainForceFilter) query.main_force_id = this.mainForceFilter;
      if (this.processManagerFilter) query.process_manager_id = this.processManagerFilter;
      if (!this.mineOnly) query.scope = "all";
      query.view = this.treeMode ? "tree" : "list";
      if (this.searchQ) query.q = this.searchQ;
      if (!this.treeMode && this.page > 1) query.page = this.page;
      if (this.sortBy !== "created_at_desc") query.sort = this.sortBy;
      this.$router.replace({ query });
    },
    async fetchTodos(options = {}) {
      const preserveOrder = Boolean(options?.preserveOrder);
      this.loading = true;
      try {
        const { data } = await api.getTodos({
          status: this.statusFilter || undefined,
          is_bug: this.bugFilter || undefined,
          sync_due: this.syncDueFilter || undefined,
          priority: this.priorityFilter || undefined,
          subtree_id: this.subtreeFilter || undefined,
          parent_id: this.parentFilter || undefined,
          main_force_id: this.mainForceFilter || undefined,
          process_manager_id: this.processManagerFilter || undefined,
          participant_id: this.mineOnly ? this.currentUserId || undefined : undefined,
          tree: this.treeMode || undefined,
          q: this.searchQ || undefined,
          page: this.page,
          size: this.size,
          sort: this.sortBy,
        });
        this.todos = preserveOrder ? this.keepCurrentTodoOrder(data.items) : data.items;
        this.total = data.total;
        this.pages = data.pages;
        this.error = "";
        this.syncQuery();
      } catch (error) {
        this.error = `加载失败：${this.errorText(error)}`;
        this.todos = [];
      } finally {
        this.loading = false;
      }
    },
    keepCurrentTodoOrder(items) {
      const previousPositions = new Map(this.todos.map((todo, index) => [todo.id, index]));
      const fallbackStart = this.todos.length;
      return items
        .map((todo, responseIndex) => ({
          todo,
          position: previousPositions.get(todo.id) ?? fallbackStart + responseIndex,
        }))
        .sort((left, right) => left.position - right.position)
        .map(entry => entry.todo);
    },
    rememberTodoPosition(todoId) {
      this.returnFocusTodoId = todoId;
      try {
        const state = {
          route: this.$route.fullPath,
          treeMode: this.treeMode,
          expandedTodoIds: this.treeMode ? this.expandedTodoIds : [],
          focusTodoId: todoId,
          scrollY: window.scrollY,
          savedAt: Date.now(),
        };
        sessionStorage.setItem(LIST_NAVIGATION_STATE_KEY, JSON.stringify(state));
      } catch {
        // Navigation still works when session storage is unavailable.
      }
    },
    restoreNavigationState() {
      try {
        const state = JSON.parse(sessionStorage.getItem(LIST_NAVIGATION_STATE_KEY) || "null");
        const expired = !state?.savedAt || Date.now() - state.savedAt > LIST_NAVIGATION_STATE_MAX_AGE;
        if (expired || state.route !== this.$route.fullPath) {
          sessionStorage.removeItem(LIST_NAVIGATION_STATE_KEY);
          return;
        }
        if (this.treeMode && state.treeMode && Array.isArray(state.expandedTodoIds)) {
          this.expandedTodoIds = state.expandedTodoIds;
        }
        this.returnFocusTodoId = state.focusTodoId || "";
        this.returnScrollY = Number.isFinite(state.scrollY) ? state.scrollY : 0;
      } catch {
        sessionStorage.removeItem(LIST_NAVIGATION_STATE_KEY);
      }
    },
    restoreNavigationPosition() {
      if (!this.returnFocusTodoId) return;
      const row = this.$el.querySelector(`[data-todo-id="${this.returnFocusTodoId}"]`);
      if (row) {
        row.scrollIntoView({ block: "center" });
        this.highlightedTodoId = this.returnFocusTodoId;
        this.highlightTimer = setTimeout(() => {
          this.highlightedTodoId = "";
        }, 2500);
      } else {
        window.scrollTo({ top: this.returnScrollY });
      }
      this.returnFocusTodoId = "";
      this.returnScrollY = 0;
      sessionStorage.removeItem(LIST_NAVIGATION_STATE_KEY);
    },
    toggleStatus(status) {
      this.statusFilter = status;
      if (status !== "pending") this.clearSyncDueFilter();
      this.search();
    },
    switchView(treeMode) {
      if (this.treeMode === treeMode) return;
      this.treeMode = treeMode;
      this.expandedTodoIds = [];
      this.page = 1;
      this.fetchTodos();
    },
    isTodoExpanded(todoId) {
      return this.expandedTodoIds.includes(todoId);
    },
    toggleTodoTree(todoId) {
      const expanded = new Set(this.expandedTodoIds);
      if (expanded.has(todoId)) expanded.delete(todoId);
      else expanded.add(todoId);
      this.expandedTodoIds = [...expanded];
    },
    treeTitleStyle(todo) {
      return this.treeMode ? { paddingLeft: `${todo._treeDepth * 22}px` } : {};
    },
    onStatusFilterChange() {
      if (this.statusFilter !== "pending") this.clearSyncDueFilter();
      this.search();
    },
    onRoleFilterChange() {
      this.mineOnly = false;
      this.search();
    },
    onMineOnlyChange() {
      if (this.mineOnly) {
        this.mainForceFilter = "";
        this.processManagerFilter = "";
      }
      this.search();
    },
    applySyncDueFilter(value) {
      this.syncDueFilter = value;
      if (value) {
        this.statusFilter = "pending";
      }
      this.search();
    },
    clearSyncDueFilter() {
      this.syncDueFilter = "";
    },
    search() {
      this.page = 1;
      this.fetchTodos();
    },
    goPage(page) {
      if (page < 1 || page > this.pages) return;
      this.page = page;
      this.fetchTodos();
    },
    openProgress(todo) {
      if (!this.canFillProgress(todo)) return;
      this.progressTodo = todo;
      this.progressContent = "";
      this.progressError = "";
      this.$nextTick(() => this.$refs.progressInput?.focus());
    },
    closeProgress() {
      if (this.progressSaving) return;
      this.progressTodo = null;
      this.progressContent = "";
      this.progressError = "";
    },
    async submitProgress() {
      const content = this.progressContent.trim();
      if (!content || !this.progressTodo) return;
      this.progressSaving = true;
      this.progressError = "";
      try {
        const { data } = await api.createTodoProgress(this.progressTodo.id, { content });
        this.closeProgressAfterSave();
        this.showSuccess(data.status_meta?.label || "进展已保存，等待确认");
        await Promise.all([this.fetchTodos({ preserveOrder: true }), this.loadStats()]);
      } catch (error) {
        this.progressError = this.errorText(error);
      } finally {
        this.progressSaving = false;
      }
    },
    closeProgressAfterSave() {
      this.progressTodo = null;
      this.progressContent = "";
      this.progressError = "";
    },
    async openSyncHistory(todo) {
      this.historyTodo = todo;
      this.historyRecords = [];
      this.historyTotal = 0;
      this.historyError = "";
      this.historyLoading = true;
      try {
        const { data } = await api.getTodoProgress(todo.id, { page: 1, size: 3 });
        if (this.historyTodo?.id !== todo.id) return;
        this.historyRecords = data.items;
        this.historyTotal = data.total;
      } catch (error) {
        if (this.historyTodo?.id === todo.id) {
          this.historyError = this.errorText(error);
        }
      } finally {
        if (this.historyTodo?.id === todo.id) {
          this.historyLoading = false;
        }
      }
    },
    closeSyncHistory() {
      this.historyTodo = null;
      this.historyRecords = [];
      this.historyTotal = 0;
      this.historyError = "";
      this.historyLoading = false;
    },
    canFillProgress(todo) {
      const autoSyncedToday = (
        todo.sync_status === "synced_today"
        && todo.last_progress_source === "children_rollup"
      );
      return todo.status === "pending" && !autoSyncedToday;
    },
    progressButtonTitle(todo) {
      if (todo.status !== "pending") return "已结束的 Todo 无需同步";
      if (todo.sync_status === "synced_today" && todo.last_progress_source === "children_rollup") {
        return "子 Todo 今日已全部同步，父 Todo 已自动汇总";
      }
      return "同步进展";
    },
    canConfirmProgress(todo) {
      return todo.status === "pending" && Boolean(todo.last_progress_id) && !todo.last_progress_confirmed_at;
    },
    async confirmProgress(todo) {
      if (!this.canConfirmProgress(todo) || this.confirmSavingId) return;
      this.confirmSavingId = todo.id;
      try {
        const { data } = await api.confirmTodoProgress(todo.id, todo.last_progress_id);
        const nextSync = this.formatDate(data.next_sync_at);
        this.showSuccess(nextSync ? `今日已同步，下次同步：${nextSync}` : "今日已同步");
        await Promise.all([this.fetchTodos({ preserveOrder: true }), this.loadStats()]);
      } catch (error) {
        window.alert(`确认失败：${this.errorText(error)}`);
      } finally {
        this.confirmSavingId = "";
      }
    },
    async completeTodo(id) {
      try {
        await api.updateTodo(id, { status: "completed" });
        this.showSuccess("Todo 已标记为完成");
        await Promise.all([this.fetchTodos({ preserveOrder: true }), this.loadStats()]);
      } catch (error) {
        window.alert(`操作失败：${this.errorText(error)}`);
      }
    },
    showSuccess(message) {
      this.successMessage = message;
      clearTimeout(this.successTimer);
      this.successTimer = setTimeout(() => { this.successMessage = ""; }, 3000);
    },
    errorText(error) {
      const detail = error.response?.data?.detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) return detail.map(item => item.msg).join("；");
      return error.message || "请求失败";
    },
    statusClass(status) {
      return {
        pending: "text-bg-warning",
        completed: "text-bg-success",
        cancelled: "text-bg-danger",
        expired: "text-bg-secondary",
      }[status] || "text-bg-secondary";
    },
    statusLabel(status) {
      return { pending: "待处理", completed: "已完成", cancelled: "已取消", expired: "已过期" }[status] || status;
    },
    syncStatusClass(tone) {
      return {
        success: "text-bg-success",
        warning: "text-bg-warning",
        danger: "text-bg-danger",
        info: "text-bg-info",
        secondary: "text-bg-secondary",
      }[tone] || "text-bg-secondary";
    },
    priorityClass(priority) {
      return {
        low: "text-bg-info",
        normal: "text-bg-primary",
        high: "text-bg-warning",
      }[priority] || "text-bg-secondary";
    },
    priorityLabel(priority) {
      return { low: "低", normal: "普通", high: "高" }[priority] || priority;
    },
    peopleText(names) {
      return names?.length ? names.join("、") : "—";
    },
    truncate(text, max) {
      if (!text) return "";
      return text.length > max ? `${text.slice(0, max)}...` : text;
    },
    formatDate(value) {
      return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "";
    },
  },
};
</script>

<style scoped>
.filter-bar {
  padding: 12px 0;
  border-top: 1px solid #dee2e6;
  border-bottom: 1px solid #dee2e6;
}

.mine-switch {
  min-height: 31px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 5px;
}

.bug-badge {
  margin-right: 5px;
  font-size: 0.65rem;
  vertical-align: 1px;
}

.mine-switch .form-check-input {
  margin-top: 0;
}

.confirm-button:not(:disabled) {
  color: #198754;
}

.sync-quick-bar {
  min-height: 38px;
  padding: 8px 10px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
}

.category-filter,
.people-filter {
  width: 150px;
}

.parent-filter {
  width: 220px;
  flex: 0 0 220px;
}

.parent-search-spinner {
  position: absolute;
  top: 7px;
  right: 8px;
  width: 14px;
  height: 14px;
}

.parent-suggestions {
  position: absolute;
  z-index: 30;
  top: calc(100% + 3px);
  left: 0;
  right: 0;
  max-height: 240px;
  overflow-y: auto;
  padding: 4px;
  background: #fff;
  border: 1px solid #ced4da;
  border-radius: 4px;
}

.parent-suggestion {
  display: block;
  width: 100%;
  padding: 6px 8px;
  overflow: hidden;
  color: #212529;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: transparent;
  border: 0;
  border-radius: 3px;
}

.parent-suggestion:hover,
.parent-suggestion:focus {
  background: #e9ecef;
  outline: 0;
}

.parent-suggestion-empty {
  padding: 8px;
  color: #6c757d;
  font-size: 13px;
  text-align: center;
}

.search-filter {
  min-width: 180px;
}

.column-menu {
  width: 210px;
}

.todo-table-wrap {
  border: 1px solid #dee2e6;
  border-radius: 6px;
}

.todo-table {
  min-width: 1050px;
  table-layout: fixed;
}

.todo-table.tree-table {
  min-width: 1075px;
}

.tree-table .title-column {
  width: 275px;
}

.tree-title {
  display: flex;
  min-width: 0;
  align-items: center;
}

.tree-toggle,
.tree-toggle-placeholder {
  flex: 0 0 24px;
  width: 24px;
  height: 24px;
}

.tree-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #495057;
  background: #fff;
  border-radius: 3px;
}

.tree-toggle:hover {
  color: #0d6efd;
  background: #e9ecef;
}

.tree-title .todo-title {
  min-width: 0;
}

.todo-table thead th {
  background: #f8f9fa;
  color: #495057;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.todo-table > :not(caption) > * > * {
  padding: 6px 5px;
}

.title-column { width: 250px; }
.category-column { width: 90px; }
.priority-column { width: 64px; }
.people-column { width: 96px; }
.sync-column { width: 170px; }
.work-status-column { width: 76px; }
.hint-column { width: 135px; }
.date-column { width: 160px; }
.frequency-column { width: 80px; }
.parent-column { width: 160px; }
.action-column { width: 52px; }

.todo-table .action-column,
.todo-table .action-cell {
  position: sticky;
  right: 0;
  z-index: 2;
  background-color: var(--bs-body-bg);
  box-shadow: -1px 0 0 #dee2e6;
}

.todo-table thead .action-column {
  z-index: 3;
  background: #f8f9fa;
}

.todo-table tbody tr:hover .action-cell {
  background: #f2f4f6;
}

.todo-table .todo-return-highlight > td,
.todo-table .todo-return-highlight > .action-cell {
  background: #fff3cd;
}

.todo-title,
.cell-text,
.status-hint {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.todo-title {
  color: #212529;
  font-weight: 500;
  text-decoration: none;
}

.todo-title:hover {
  color: #0d6efd;
  text-decoration: underline;
}

.cell-text,
.status-hint {
  color: #6c757d;
  font-size: 13px;
}

.sync-state {
  min-height: 28px;
}

.sync-state .badge {
  white-space: nowrap;
  font-size: 11px;
}

.sync-button,
.icon-button {
  width: 28px;
  height: 28px;
  padding: 0;
}

.sync-button {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  color: #495057;
  text-decoration: none;
}

.modal {
  z-index: 1060;
  background: transparent;
}

.modal-backdrop {
  z-index: 1055;
}

.modal-todo-title {
  max-width: 390px;
}

.progress-prompt {
  padding: 12px;
  border-left: 3px solid #6c757d;
  background: #f8f9fa;
  white-space: pre-wrap;
}

.sync-history-content {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.sync-history-revoked {
  opacity: 0.65;
}

@media (max-width: 767.98px) {
  .parent-filter,
  .category-filter,
  .people-filter,
  .search-filter {
    width: 100%;
    flex: 0 0 100%;
  }
}
</style>
