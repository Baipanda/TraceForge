<template>
  <div v-if="todo">
    <div class="d-flex align-items-center mb-3">
      <button class="btn btn-sm btn-outline-secondary me-2" @click="$router.back()">
        <i class="bi bi-arrow-left"></i> 返回
      </button>
      <h4 class="mb-0 flex-grow-1">{{ todo.title }}</h4>
      <button class="btn btn-sm btn-outline-primary" @click="editing = !editing">
        <i class="bi" :class="editing ? 'bi-eye' : 'bi-pencil'"></i>
        {{ editing ? "查看" : "编辑" }}
      </button>
    </div>

    <!-- View Mode -->
    <div v-if="!editing">
      <div class="row g-3">
        <!-- Left -->
        <div class="col-md-8">
          <div class="card mb-3">
            <div class="card-body">
              <h6 class="card-subtitle mb-2 text-muted">描述</h6>
              <p class="card-text" style="white-space:pre-wrap">{{ todo.description || "无描述" }}</p>
            </div>
          </div>
          <div class="card mb-3">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-center mb-3">
                <h6 class="card-subtitle mb-0 text-muted">进展历史</h6>
                <small class="text-muted">{{ progressTotal }} 条</small>
              </div>
              <div v-if="progressLoading && progressRecords.length === 0" class="text-center py-3">
                <div class="spinner-border spinner-border-sm"></div>
              </div>
              <div v-else-if="progressRecords.length" class="progress-timeline">
                <div
                  v-for="entry in progressRecords"
                  :key="entry.id"
                  class="progress-entry"
                  :class="{ 'progress-entry-revoked': entry.revoked_at }"
                >
                  <div class="d-flex flex-wrap gap-2 align-items-center mb-1">
                    <strong class="small">{{ entry.recorded_by_name }}</strong>
                    <small class="text-muted">{{ formatDate(entry.recorded_at) }}</small>
                    <span v-if="entry.source === 'children_rollup'" class="badge text-bg-info">系统汇总</span>
                    <span v-if="entry.revoked_at" class="badge text-bg-secondary">已失效</span>
                    <span v-else-if="entry.confirmed_at" class="badge text-bg-success">已确认</span>
                    <span v-else class="badge text-bg-warning">待确认</span>
                  </div>
                  <div class="small progress-content">{{ entry.content }}</div>
                  <small v-if="entry.confirmed_at && !entry.revoked_at" class="text-muted d-block mt-1">
                    {{ entry.confirmed_by_name }} 于 {{ formatDate(entry.confirmed_at) }} 确认同步
                  </small>
                  <small v-else-if="entry.revoked_at" class="text-muted d-block mt-1">
                    子 Todo 状态发生变化，此次自动汇总于 {{ formatDate(entry.revoked_at) }} 失效
                  </small>
                </div>
                <button
                  v-if="progressPage < progressPages"
                  type="button"
                  class="btn btn-sm btn-outline-secondary"
                  :disabled="progressLoading"
                  @click="loadMoreProgress"
                >
                  <span v-if="progressLoading" class="spinner-border spinner-border-sm me-1"></span>
                  加载更多
                </button>
              </div>
              <div v-else class="text-muted small py-2">暂无同步进展</div>
              <div v-if="progressError" class="text-danger small mt-2">{{ progressError }}</div>
            </div>
          </div>
          <div class="card mb-3" v-if="todo.children.length">
            <div class="card-body">
              <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
                <h6 class="card-subtitle mb-0 text-muted">子 Todo ({{ todo.children.length }})</h6>
                <div class="small" :class="childWeightSummaryClass">
                  子项合计 {{ childWeightTotal }}%，父 Todo 自身 {{ parentOwnWeight }}%
                </div>
              </div>
              <div class="table-responsive">
                <table class="table table-sm align-middle mb-2 child-weight-table">
                  <thead>
                    <tr>
                      <th>子 Todo</th>
                      <th class="child-status-cell">状态</th>
                      <th class="child-weight-cell">占比</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="c in todo.children" :key="c.id">
                      <td>
                        <router-link :to="`/todos/${c.id}`">
                          <span v-if="c.is_bug" class="badge text-bg-danger me-1">BUG</span>{{ c.title }}
                        </router-link>
                      </td>
                      <td><span class="badge" :class="statusClass(c.status)">{{ statusLabel(c.status) }}</span></td>
                      <td>
                        <div class="input-group input-group-sm child-weight-input">
                          <input
                            v-model.number="childWeights[c.id]"
                            class="form-control text-end"
                            type="number"
                            min="0"
                            max="100"
                            step="1"
                            inputmode="numeric"
                            :aria-label="`${c.title} 占比`"
                          />
                          <span class="input-group-text">%</span>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="d-flex flex-wrap align-items-center justify-content-between gap-2">
                <div class="small">
                  <span v-if="childWeightError" class="text-danger">{{ childWeightError }}</span>
                  <span v-else-if="!childWeightsValid" class="text-danger">占比必须是 0～100 的整数，合计不能超过 100%</span>
                  <span v-else-if="childWeightTotal === 100" class="text-success">子 Todo 已覆盖全部工作</span>
                  <span v-else class="text-muted">父 Todo 完成剩余 {{ parentOwnWeight }}% 后需手动标记完成</span>
                </div>
                <button
                  type="button"
                  class="btn btn-sm btn-outline-primary"
                  :disabled="childWeightSaving || !childWeightsValid || !childWeightsChanged"
                  @click="saveChildWeights"
                >
                  <span v-if="childWeightSaving" class="spinner-border spinner-border-sm me-1"></span>
                  <i v-else class="bi bi-save me-1"></i>保存占比
                </button>
              </div>
            </div>
          </div>
          <div class="card mb-3" v-if="todo.depends_on_details.length">
            <div class="card-body">
              <h6 class="card-subtitle mb-2 text-muted">依赖项</h6>
              <ul class="list-group list-group-flush">
                <li class="list-group-item" v-for="d in todo.depends_on_details" :key="d.id">
                  <router-link :to="`/todos/${d.id}`">{{ d.title }}</router-link>
                  <span class="badge ms-2" :class="statusClass(d.status)">{{ d.status }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
        <!-- Right -->
        <div class="col-md-4">
          <div class="card mb-3">
            <div class="card-body">
              <dl class="row mb-0 small">
                <dt class="col-sm-4">Todo ID</dt>
                <dd class="col-sm-8">
                  <code class="text-muted small" style="word-break:break-all">{{ todo.id }}</code>
                </dd>

                <dt class="col-sm-4">状态</dt>
                <dd class="col-sm-8">
                  <span class="badge" :class="statusClass(todo.status)">{{ statusLabel(todo.status) }}</span>
                  <div v-if="todo.auto_completed_by_children" class="text-muted mt-1">所有子 Todo 均已结束，系统自动完成</div>
                </dd>

                <dt class="col-sm-4">事项类型</dt>
                <dd class="col-sm-8">
                  <span v-if="todo.is_bug" class="badge text-bg-danger">BUG</span>
                  <span v-else>普通 Todo</span>
                </dd>

                <dt class="col-sm-4">同步状态</dt>
                <dd class="col-sm-8">
                  <span class="badge" :class="syncStatusClass(todo.status_meta?.tone)">{{ todo.status_meta?.label }}</span>
                  <div class="text-muted mt-1">{{ todo.status_meta?.hint }}</div>
                </dd>

                <dt class="col-sm-4">优先级</dt>
                <dd class="col-sm-8"><span class="badge" :class="priorityClass(todo.priority)">{{ priorityLabel(todo.priority) }}</span></dd>

                <dt class="col-sm-4">分类</dt>
                <dd class="col-sm-8">{{ todo.subtree_name }}</dd>

                <dt class="col-sm-4">父 Todo</dt>
                <dd class="col-sm-8">
                  <router-link v-if="todo.parent_id && todo.parent_title" :to="`/todos/${todo.parent_id}`">
                    {{ todo.parent_title }}
                  </router-link>
                  <span v-else-if="todo.parent_id" class="text-muted">(已删除)</span>
                  <span v-else class="text-muted">—</span>
                </dd>

                <template v-if="todo.parent_id">
                  <dt class="col-sm-4">在父项中占比</dt>
                  <dd class="col-sm-8">{{ todo.parent_weight_percent ?? 0 }}%</dd>
                </template>

                <dt class="col-sm-4">项目</dt>
                <dd class="col-sm-8">{{ todo.project_name || "—" }}</dd>

                <dt class="col-sm-4">主力人员</dt>
                <dd class="col-sm-8">{{ peopleText(todo.main_force_names) }}</dd>

                <dt class="col-sm-4">流程管理</dt>
                <dd class="col-sm-8">{{ peopleText(todo.process_manager_names) }}</dd>

                <dt class="col-sm-4">同步频率</dt>
                <dd class="col-sm-8">{{ todo.track_frequency_label || "—" }}</dd>

                <dt class="col-sm-4">下次同步</dt>
                <dd class="col-sm-8">{{ todo.next_sync_at ? formatDate(todo.next_sync_at) : "—" }}</dd>

                <dt class="col-sm-4">进展提示</dt>
                <dd class="col-sm-8 progress-prompt-text">{{ todo.progress_prompt }}</dd>

                <dt class="col-sm-4">创建时间</dt>
                <dd class="col-sm-8">{{ formatDate(todo.created_at) }}</dd>

                <dt class="col-sm-4">更新时间</dt>
                <dd class="col-sm-8">{{ formatDate(todo.updated_at) }}</dd>

                <dt class="col-sm-4">完成时间</dt>
                <dd class="col-sm-8">{{ todo.completed_at ? formatDate(todo.completed_at) : "—" }}</dd>
              </dl>
            </div>
          </div>

          <!-- People arrays -->
          <div class="card mb-3" v-if="todo.watcher_names.length">
            <div class="card-body py-2 small">
              <strong>关注人:</strong> {{ todo.watcher_names.join("、") }}
            </div>
          </div>
          <div class="card mb-3" v-if="todo.technical_advisor_names.length">
            <div class="card-body py-2 small">
              <strong>技术顾问:</strong> {{ todo.technical_advisor_names.join("、") }}
            </div>
          </div>
          <div class="card mb-3" v-if="todo.backup_force_names.length">
            <div class="card-body py-2 small">
              <strong>后备力量:</strong> {{ todo.backup_force_names.join("、") }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Edit Mode -->
    <TodoForm v-else :todo="todo" :editing="true" @saved="onSaved" @cancel="editing = false" />
  </div>
  <div v-else-if="loading" class="text-center py-5">
    <div class="spinner-border"></div>
  </div>
  <div v-else class="text-center py-5 text-muted">
    Todo 未找到
  </div>
</template>

<script>
import api from "../api/index.js";
import TodoForm from "../components/TodoForm.vue";

export default {
  name: "TodoDetail",
  components: { TodoForm },
  props: ["id"],
  data() {
    return {
      todo: null,
      loading: true,
      editing: false,
      progressRecords: [],
      progressTotal: 0,
      progressPage: 1,
      progressPages: 0,
      progressLoading: false,
      progressError: "",
      childWeights: {},
      childWeightSaving: false,
      childWeightError: "",
    };
  },
  computed: {
    childWeightTotal() {
      return this.todo?.children.reduce(
        (total, child) => total + this.childWeightValue(child.id),
        0,
      ) || 0;
    },
    parentOwnWeight() {
      return Math.max(0, 100 - this.childWeightTotal);
    },
    childWeightsValid() {
      if (!this.todo?.children.length) return false;
      const valuesValid = this.todo.children.every((child) => {
        const value = Number(this.childWeights[child.id]);
        return Number.isInteger(value) && value >= 0 && value <= 100;
      });
      return valuesValid && this.childWeightTotal <= 100;
    },
    childWeightsChanged() {
      return Boolean(this.todo?.children.some(
        (child) => this.childWeightValue(child.id) !== (child.parent_weight_percent || 0),
      ));
    },
    childWeightSummaryClass() {
      if (!this.childWeightsValid) return "text-danger";
      return this.childWeightTotal === 100 ? "text-success" : "text-warning-emphasis";
    },
  },
  async mounted() {
    await this.loadTodo();
  },
  watch: {
    id() {
      this.editing = false;
      this.loadTodo();
    },
  },
  methods: {
    async loadTodo() {
      this.loading = true;
      this.progressRecords = [];
      this.progressPage = 1;
      try {
        const res = await api.getTodo(this.id);
        this.todo = res.data;
        this.resetChildWeights();
        await this.loadProgress();
      } catch (e) {
        this.todo = null;
      }
      this.loading = false;
    },
    onSaved() {
      this.editing = false;
      this.loadTodo();
    },
    async loadProgress(append = false) {
      this.progressLoading = true;
      this.progressError = "";
      try {
        const { data } = await api.getTodoProgress(this.id, { page: this.progressPage, size: 20 });
        this.progressRecords = append ? [...this.progressRecords, ...data.items] : data.items;
        this.progressTotal = data.total;
        this.progressPages = data.pages;
      } catch (error) {
        this.progressError = error.response?.data?.detail || error.message || "进展历史加载失败";
      } finally {
        this.progressLoading = false;
      }
    },
    async loadMoreProgress() {
      if (this.progressLoading || this.progressPage >= this.progressPages) return;
      this.progressPage += 1;
      await this.loadProgress(true);
    },
    childWeightValue(childId) {
      const value = Number(this.childWeights[childId]);
      return Number.isFinite(value) ? value : 0;
    },
    resetChildWeights() {
      this.childWeights = Object.fromEntries(
        (this.todo?.children || []).map((child) => [
          child.id,
          child.parent_weight_percent || 0,
        ]),
      );
      this.childWeightError = "";
    },
    async saveChildWeights() {
      if (!this.childWeightsValid || !this.childWeightsChanged || this.childWeightSaving) return;
      this.childWeightSaving = true;
      this.childWeightError = "";
      try {
        const items = this.todo.children.map((child) => ({
          todo_id: child.id,
          percent: this.childWeightValue(child.id),
        }));
        const { data } = await api.updateChildWeights(this.todo.id, { items });
        this.todo = data;
        this.resetChildWeights();
      } catch (error) {
        this.childWeightError = error.response?.data?.detail || error.message || "占比保存失败";
      } finally {
        this.childWeightSaving = false;
      }
    },
    statusClass(s) {
      return { pending: "bg-warning text-dark", completed: "bg-success", cancelled: "bg-danger" }[s] || "bg-secondary";
    },
    statusLabel(s) {
      return { pending: "Pending", completed: "Completed", cancelled: "Cancelled", expired: "Expired" }[s] || s;
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
    priorityClass(p) {
      return {
        low: "text-bg-info",
        normal: "text-bg-primary",
        high: "text-bg-warning",
      }[p] || "text-bg-secondary";
    },
    priorityLabel(p) {
      return { low: "Low", normal: "Normal", high: "High" }[p] || p;
    },
    peopleText(names) {
      return names && names.length ? names.join("、") : "—";
    },
    formatDate(d) {
      return d ? new Date(d).toLocaleString("zh-CN") : "";
    },
  },
};
</script>

<style scoped>
.progress-timeline {
  border-left: 2px solid #dee2e6;
  margin-left: 6px;
  padding-left: 18px;
}

.progress-entry {
  position: relative;
  padding-bottom: 18px;
}

.progress-entry::before {
  position: absolute;
  top: 5px;
  left: -24px;
  width: 10px;
  height: 10px;
  content: "";
  background: #6c757d;
  border: 2px solid #fff;
  border-radius: 50%;
}

.progress-entry-revoked {
  opacity: 0.65;
}

.progress-content,
.progress-prompt-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.child-weight-table {
  table-layout: fixed;
}

.child-status-cell {
  width: 92px;
}

.child-weight-cell {
  width: 120px;
}

.child-weight-input {
  width: 104px;
}
</style>
