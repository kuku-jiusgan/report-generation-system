<script setup lang="ts">
import {
  Clock,
  CopyDocument,
  Delete,
  Document,
  EditPen,
  Plus,
  Refresh,
} from "@element-plus/icons-vue";
import type { AdminTemplate, AdminTemplateVersion } from "./admin-api";
import { templateVersionStatusText as statusText, useTemplateLibrary } from "./composables/useTemplateLibrary";

const emit = defineEmits<{
  open: [template: AdminTemplate, version: AdminTemplateVersion];
}>();
const {
  templates, versions, selected, editingTemplate, loading, versionLoading,
  deletingTemplate, savingTemplate, savingVersion, activatingVersionId,
  templateDialog, versionDialog, templateDraft, versionDraft, selectedTitle,
  loadTemplates, selectTemplate, openCreateTemplate, openEditTemplate,
  saveTemplate, removeTemplate, openCreateVersion, saveVersion, enterDesigner,
} = useTemplateLibrary((template, version) => emit("open", template, version));
</script>

<template>
  <div class="template-library">
    <header class="module-header">
      <div class="module-title">
        <Document />
        <div><strong>报告模板规则</strong><small>模板、版本与 Word 映射规则</small></div>
      </div>
      <div class="library-actions">
        <el-button :icon="Refresh" @click="loadTemplates()">刷新</el-button
        ><el-button type="primary" :icon="Plus" @click="openCreateTemplate"
          >新建模板</el-button
        >
      </div>
    </header>

    <main class="library-workspace">
      <aside class="template-index">
        <div class="index-heading">
          <div>
            <h1>模板库</h1>
            <p>{{ templates.length }} 个报告模板</p>
          </div>
          <el-button
            text
            :icon="Plus"
            aria-label="新建模板"
            @click="openCreateTemplate"
          />
        </div>
        <el-skeleton v-if="loading" :rows="5" animated />
        <div v-else class="template-list">
          <button
            v-for="item in templates"
            :key="item.id"
            :class="{ selected: selected?.id === item.id }"
            @click="selectTemplate(item)"
          >
            <span class="template-icon"><Document /></span>
            <span
              ><b>{{ item.name }}</b
              ><small
                >{{ item.code }} · {{ item.versionCount }} 个版本</small
              ></span
            >
            <el-tag v-if="item.publishedVersion" size="small" type="success"
              >V{{ item.publishedVersion }}</el-tag
            >
            <el-tag v-else size="small" type="info">未发布</el-tag>
          </button>
          <div v-if="!templates.length" class="library-empty">
            <Document /><strong>还没有报告模板</strong>
            <p>新建模板后会自动创建第一个草稿版本。</p>
          </div>
        </div>
      </aside>

      <section class="version-workspace">
        <div v-if="selected" class="version-heading">
          <div>
            <div class="path">模板库 / {{ selected.code }}</div>
            <h1>{{ selectedTitle }}</h1>
            <p>{{ selected.description || "尚未填写模板用途说明" }}</p>
          </div>
          <div>
            <el-button :icon="EditPen" @click="openEditTemplate"
              >编辑模板信息</el-button
            ><el-button
              type="danger"
              plain
              :icon="Delete"
              :loading="deletingTemplate"
              @click="removeTemplate"
              >删除模板</el-button
            ><el-button type="primary" :icon="Plus" @click="openCreateVersion()"
              >新建版本</el-button
            >
          </div>
        </div>
        <div v-if="selected" class="version-summary">
          <span
            ><b>{{ selected.versionCount }}</b
            >全部版本</span
          ><span
            ><b>{{ selected.latestVersion || "-" }}</b
            >最新版本</span
          ><span
            ><b>{{ selected.publishedVersion || "-" }}</b
            >当前发布</span
          ><span
            ><b>{{
              new Date(selected.updatedAt).toLocaleDateString("zh-CN")
            }}</b
            >最近更新</span
          >
        </div>
        <div v-if="selected" class="version-table-wrap">
          <div class="table-title">
            <div>
              <h2>版本记录</h2>
              <p>点击具体版本进入报告模板设计器</p>
            </div>
          </div>
          <el-table v-loading="versionLoading" :data="versions" row-key="id">
            <el-table-column label="版本" width="110"
              ><template #default="scope"
                ><strong class="version-no"
                  >V{{ scope.row.versionNo }}</strong
                ></template
              ></el-table-column
            >
            <el-table-column label="状态" width="120"
              ><template #default="scope"
                ><el-tag
                  :type="
                    scope.row.status === 'PUBLISHED'
                      ? 'success'
                      : scope.row.status === 'DRAFT'
                        ? 'primary'
                        : 'info'
                  "
                  effect="plain"
                  >{{ statusText[scope.row.status] }}</el-tag
                ></template
              ></el-table-column
            >
            <el-table-column prop="note" label="版本说明" min-width="260" />
            <el-table-column label="更新时间" width="190"
              ><template #default="scope"
                ><span class="time-cell"
                  ><Clock />{{
                    new Date(scope.row.updatedAt).toLocaleString("zh-CN")
                  }}</span
                ></template
              ></el-table-column
            >
            <el-table-column
              label="操作"
              width="300"
              fixed="right"
              align="right"
            >
              <template #default="scope">
                <div class="version-row-actions">
                  <el-button
                    type="primary"
                    plain
                    :loading="activatingVersionId === scope.row.id"
                    @click="enterDesigner(scope.row)"
                    >进入设计器</el-button
                  >
                  <el-button
                    :icon="CopyDocument"
                    @click="openCreateVersion(scope.row)"
                    >基于此版本新建</el-button
                  >
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div v-else class="workspace-empty">
          <Document />
          <h2>请选择模板</h2>
          <p>模板版本、发布状态和设计入口会显示在这里。</p>
        </div>
      </section>
    </main>

    <el-dialog
      v-model="templateDialog"
      :title="editingTemplate ? '编辑模板信息' : '新建报告模板'"
      width="560px"
    >
      <el-form label-position="top"
        ><div class="dialog-grid">
          <el-form-item label="模板编码"
            ><el-input
              v-model="templateDraft.code"
              placeholder="例如 METHOD-VALIDATION" /></el-form-item
          ><el-form-item label="模板名称"
            ><el-input
              v-model="templateDraft.name"
              placeholder="例如 分析方法验证报告"
          /></el-form-item>
        </div>
        <el-form-item label="用途说明"
          ><el-input
            v-model="templateDraft.description"
            type="textarea"
            :rows="4"
            placeholder="说明该模板适用的报告类型和范围" /></el-form-item
        ><el-alert
          v-if="!editingTemplate"
          title="新模板会使用初始 Word 文件创建独立的 V1；章节和字段规则可在设计器中单独配置。"
          type="info"
          :closable="false"
      /></el-form>
      <template #footer
        ><el-button @click="templateDialog = false">取消</el-button
        ><el-button type="primary" :loading="savingTemplate" @click="saveTemplate">{{
          editingTemplate ? "保存修改" : "创建模板"
        }}</el-button></template
      >
    </el-dialog>

    <el-dialog v-model="versionDialog" title="新建模板版本" width="520px">
      <el-form label-position="top"
        ><el-form-item label="基础版本"
          ><el-select
            v-model="versionDraft.baseVersionId"
            placeholder="选择要复制的版本"
            ><el-option
              v-for="item in versions"
              :key="item.id"
              :label="`V${item.versionNo} · ${statusText[item.status]}`"
              :value="item.id" /></el-select></el-form-item
        ><el-form-item label="版本说明"
          ><el-input
            v-model="versionDraft.note"
            type="textarea"
            :rows="3" /></el-form-item
      ></el-form>
      <template #footer
        ><el-button @click="versionDialog = false">取消</el-button
        ><el-button type="primary" :loading="savingVersion" @click="saveVersion"
          >创建草稿版本</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>

<style scoped>
.template-library {
  height: 100%;
  min-width: 0;
  color: #263731;
  background: #f4f7fb;
  overflow: hidden;
}
.module-header {
  height: 64px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #e4eaf2;
}
.module-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.module-title > svg {
  width: 22px;
  color: #2167e8;
}
.module-title strong,
.module-title small {
  display: block;
}
.module-title strong {
  color: #263548;
  font-size: 14px;
}
.module-title small {
  margin-top: 3px;
  color: #6b7c75;
  font-size: 10px;
}
.library-actions {
  margin-left: auto;
  display: flex;
  gap: 7px;
}
.library-actions .el-button {
  margin: 0;
}
.library-workspace {
  height: calc(100% - 64px);
  display: grid;
  grid-template-columns: 290px minmax(0, 1fr);
}
.template-index {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-right: 1px solid #e4eaf2;
}
.index-heading {
  height: 78px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e2e7e4;
}
.index-heading h1,
.version-heading h1,
.table-title h2 {
  margin: 0;
  color: #263548;
}
.index-heading h1 {
  font-size: 18px;
}
.index-heading p,
.version-heading p,
.table-title p {
  margin: 5px 0 0;
  color: #697a74;
  font-size: 11px;
}
.template-index > .el-skeleton {
  padding: 18px;
}
.template-list {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 10px;
}
.template-list > button {
  width: 100%;
  min-height: 64px;
  padding: 10px;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  border: 0;
  border-bottom: 1px solid #e7ebe9;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: background-color 180ms ease-out;
}
.template-list > button:hover {
  background: #f1f6f4;
}
.template-list > button.selected {
  background: #e5f0ed;
  box-shadow: inset 3px 0 #216b5a;
}
.template-icon {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  color: #fff;
  background: #337965;
}
.template-icon svg {
  width: 17px;
}
.template-list b,
.template-list small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.template-list b {
  font-size: 12px;
}
.template-list small {
  margin-top: 5px;
  color: #71817b;
  font-size: 10px;
}
.version-workspace {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 24px 28px;
}
.version-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}
.version-heading > div:last-child {
  display: flex;
  gap: 8px;
}
.version-heading h1 {
  margin-top: 8px;
  font-size: 24px;
}
.path {
  color: #73847e;
  font-size: 10px;
}
.version-summary {
  margin-top: 24px;
  display: flex;
  border-top: 1px solid #cfd8d4;
  border-bottom: 1px solid #cfd8d4;
  background: #f7f9fc;
}
.version-summary span {
  min-width: 150px;
  padding: 14px 20px;
  color: #687972;
  font-size: 10px;
  border-right: 1px solid #d7dfdb;
}
.version-summary b {
  display: block;
  margin-bottom: 5px;
  color: #1d4b40;
  font-size: 17px;
}
.version-table-wrap {
  margin-top: 22px;
  background: #fff;
  border: 1px solid #d7dfdb;
}
.table-title {
  padding: 18px 20px;
  border-bottom: 1px solid #e2e7e4;
}
.table-title h2 {
  font-size: 15px;
}
.version-no {
  color: #1f5f50;
  font-size: 14px;
}
.time-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #63736d;
}
.time-cell svg {
  width: 14px;
}
.version-row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  white-space: nowrap;
}
.version-row-actions .el-button {
  flex: 0 0 auto;
  margin: 0;
}
.library-empty,
.workspace-empty {
  padding: 70px 24px;
  color: #6b7c75;
  text-align: center;
}
.library-empty svg,
.workspace-empty svg {
  width: 32px;
}
.library-empty strong {
  display: block;
  margin-top: 10px;
}
.library-empty p,
.workspace-empty p {
  font-size: 11px;
}
.workspace-empty h2 {
  font-size: 18px;
}
.dialog-grid {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 10px;
}
@media (max-width: 1250px) {
  .library-workspace {
    grid-template-columns: 270px minmax(0, 1fr);
  }
  .version-workspace {
    padding: 24px;
  }
  .version-summary span {
    min-width: 125px;
    padding-inline: 14px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .template-list > button {
    transition: none;
  }
}
</style>
