<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue"; import { ElMessage, ElMessageBox } from "element-plus";
import {
  adminApi,
  type AdminTemplate,
  type AdminTemplateVersion,
  type ContentBlockKind,
  type DataSourceRule,
  type DesignerBlock,
  type DesignerChapter,
  type LimsImport,
  type LimsRecognitionTest,
  type MappingRule,
  type RuleVersion,
  type StandardField,
  type TableRule,
  type TemplateDesigner,
  type ValidationReport,
} from "./admin-api";
import type { AuthUser } from "./auth-api";
import {
  adminErrorText as errorText,
  chapterTitle as codeTitle,
  firstAnchoredMapping,
} from "./admin/designer-formatters";
import { mappingDisplayName, mappingIdentifiers } from "./admin/mapping-identifiers";
import {
  controlId,
  controlTag,
  useAdminWordEditor,
  type WordControl as Control,
} from "./composables/useAdminWordEditor";
import { useDesignerDrag } from "./composables/useDesignerDrag";
import { useChapterBlockEditor } from "./composables/useChapterBlockEditor";
import { useAdminPublishing } from "./composables/useAdminPublishing";
import { useCalculationEditor } from "./composables/useCalculationEditor";
import { useMappingEditor } from "./composables/useMappingEditor";
import AdminSourcesView from "./admin/AdminSourcesView.vue";
import AdminVersionsView from "./admin/AdminVersionsView.vue";
import AdminStructureDialogs from "./admin/AdminStructureDialogs.vue";
import AdminSourceDialogs from "./admin/AdminSourceDialogs.vue";
import AdminValidationDialog from "./admin/AdminValidationDialog.vue";
import AdminDesignerHeader from "./admin/AdminDesignerHeader.vue";
import AdminWordCanvas from "./admin/AdminWordCanvas.vue";
import AdminChapterTree from "./admin/AdminChapterTree.vue";
import AdminInspectorPanel from "./admin/AdminInspectorPanel.vue";
defineProps<{
  catalogTemplate?: AdminTemplate;
  catalogVersion?: AdminTemplateVersion;
  sessionUser: AuthUser;
}>();
defineEmits<{ back: []; logout: [] }>();
type WorkspaceMode = "designer" | "sources" | "versions";

const loading = ref(true);
const workspaceMode = ref<WorkspaceMode>("designer");
const designer = ref<TemplateDesigner>();
const sources = ref<DataSourceRule[]>([]);
const standardFields = ref<StandardField[]>([]);
const versions = ref<RuleVersion[]>([]);
const limsImports = ref<LimsImport[]>([]);
const search = ref("");
const expanded = ref<number[]>([]);
const selectedChapter = ref<DesignerChapter>();
const selectedBlock = ref<DesignerBlock>();
const expandedContentBlockId = ref<number>();
const selectedMapping = ref<MappingRule>();
const mappingDraft = ref<Partial<MappingRule>>({});
const advancedOpen = ref(false);
const saving = ref(false);
const bindingMappingId = ref<number>();
const unbindingWord = ref(false);
const detectingTable = ref(false);
const {
  ready: wordReady,
  loading: onlyOfficeLoading,
  error: onlyOfficeError,
  linkState: wordLinkState,
  controls,
  pluginReady,
  hasConnector,
  exec: execWord,
  refreshControls: refreshWordControls,
  requestBind: requestWordBind,
  requestUnbind: requestPluginUnbind,
  requestTableDetection,
  locate: locateInWord,
  open: openOnlyOffice,
  close: closeOnlyOffice,
} = useAdminWordEditor(handleWordTag);

async function detectCurrentTable() {
  if (!wordReady.value || !pluginReady.value) {
    ElMessage.warning('Word 编辑器尚未连接，请先打开模板编辑器')
    return
  }
  detectingTable.value = true
  try {
    const index = await requestTableDetection()
    if (!Number.isInteger(index) || index < 1) {
      ElMessage.warning('未识别到当前表格，请将光标放在目标表格内')
      return
    }
    await ElMessageBox.confirm(`识别到当前表格为第 ${index} 张，确认写入布局配置吗？`, '确认表格', { type: 'info' })
    if (blockDraft.value?.tableRule) blockDraft.value.tableRule.physicalTableIndex = index
    ElMessage.success(`已确认第 ${index} 张表格`)
  } catch (error) {
    if (String(error).includes('cancel')) return
    ElMessage.error('当前 OnlyOffice 版本不支持自动识别表格，请手动填写序号')
  } finally {
    detectingTable.value = false
  }
}
const {
  draggingBlockId,
  dragOverBlockId,
  draggingMappingId,
  dragOverMappingId,
  reordering,
  startBlockDrag,
  dropBlock,
  startMappingDrag,
  dropMapping,
  finishDrag,
} = useDesignerDrag(selectedChapter, () => loadDesigner(true));
const {
  chapterDraft,
  chapterDialog,
  blockDialog,
  blockDraft,
  editChapter,
  saveChapter,
  saveChapterFromInspector,
  removeChapter,
  editBlock,
  saveBlock,
  removeBlock,
} = useChapterBlockEditor({
  designer,
  selectedChapter,
  saving,
  reload: () => loadDesigner(true),
  selectBlock,
});
const {
  sourceDialog,
  sourceDraft,
  sourceConfigText,
  validation,
  validationDialog,
  validating,
  publishing,
  recognitionDialog,
  recognitionResultDialog,
  recognitionImport,
  recognitionIds,
  recognitionTesting,
  recognitionResult,
  editSource,
  saveSource,
  validateRules,
  publishRules,
  openRecognition,
  runRecognition,
} = useAdminPublishing({
  sources,
  versions,
  limsImports,
  reloadDesigner: () => loadDesigner(true),
});
const {
  onSourceTypeChange,
  insertCalculationText,
  insertCalculationReference,
  insertCalculationFunction,
  selectStandardField,
} = useCalculationEditor(mappingDraft, selectedBlock);
const { addMapping, saveMapping, removeMapping, saveTableRule } = useMappingEditor({
  designer,
  selectedChapter,
  selectedBlock,
  selectedMapping,
  expandedBlockId: expandedContentBlockId,
  draft: mappingDraft,
  saving,
  reload: () => loadDesigner(true),
  identifiers: generateMappingIdentifiers,
  displayName: generateMappingDisplayName,
  selectMapping,
});
const blockKindOptions: Array<{ value: ContentBlockKind; label: string }> = [
  { value: "FIXED", label: "固定内容" },
  { value: "MAPPED_FIELD", label: "单值字段组" },
  { value: "REPEATING_TABLE", label: "循环表格" },
  { value: "MATRIX", label: "结果矩阵" },
  { value: "TABLE_REPEAT", label: "按杂质复制整表" },
  { value: "AI_NARRATIVE", label: "AI 文本块" },
  { value: "CALCULATED", label: "计算内容块" },
];
const flatten = (items: DesignerChapter[]): DesignerChapter[] =>
  items.flatMap((item) => [item, ...flatten(item.children)]);

const filteredChapters = computed(() => {
  const query = search.value.trim().toLowerCase();
  const visit = (item: DesignerChapter): DesignerChapter | undefined => {
    const children = item.children
      .map(visit)
      .filter(Boolean) as DesignerChapter[];
    const own =
      `${item.code} ${item.title} ${item.blocks.map((block) => `${block.title} ${block.mappings.map((mapping) => `${mapping.wordLabel} ${mapping.fieldCode}`).join(" ")}`).join(" ")}`.toLowerCase();
    return !query || own.includes(query) || children.length
      ? { ...item, children }
      : undefined;
  };
  return (designer.value?.chapters || [])
    .map(visit)
    .filter(Boolean) as DesignerChapter[];
});
const calculationFieldOptions = computed(() =>
  flatten(designer.value?.chapters || []).flatMap((chapter) =>
    chapter.blocks.flatMap((block) =>
      block.mappings
        .filter(
          (mapping) =>
            mapping.id !== selectedMapping.value?.id && Boolean(mapping.fieldCode),
        )
        .map((mapping) => ({
          code: mapping.fieldCode,
          label: `${chapter.code} ${chapter.title} / ${block.title} / ${mapping.wordLabel}`,
        })),
    ),
  ),
);
function selectChapter(chapter: DesignerChapter) {
  selectedChapter.value = chapter;
  selectedBlock.value = undefined;
  expandedContentBlockId.value = undefined;
  selectMapping(undefined, false);
}
function selectBlock(
  chapter: DesignerChapter,
  block: DesignerBlock,
  locate = true,
) {
  selectedChapter.value = chapter;
  selectedBlock.value = block;
  expandedContentBlockId.value = block.id;
  selectMapping(block.mappings[0], locate);
}
function toggleContentBlock(chapter: DesignerChapter, block: DesignerBlock) {
  selectedChapter.value = chapter;
  selectedBlock.value = block;
  if (expandedContentBlockId.value === block.id) {
    expandedContentBlockId.value = undefined;
    return;
  }
  expandedContentBlockId.value = block.id;
  selectMapping(block.mappings[0], true);
}
function selectMapping(mapping?: MappingRule, locate = true) {
  selectedMapping.value = mapping;
  mappingDraft.value = mapping
    ? JSON.parse(JSON.stringify(mapping))
    : undefined;
  if (mapping && locate) void locateInWord(mapping.controlTag);
}

async function loadDesigner(preserve = true) {
  const chapterId = preserve ? selectedChapter.value?.id : undefined;
  const blockId = preserve ? selectedBlock.value?.id : undefined;
  const mappingId = preserve ? selectedMapping.value?.id : undefined;
  const [currentDesigner, currentStandardFields] = await Promise.all([
    adminApi.designer(),
    adminApi.standardFields(),
  ]);
  designer.value = currentDesigner;
  standardFields.value = currentStandardFields;
  expanded.value = flatten(designer.value.chapters).map((item) => item.id);
  const chapter =
    flatten(designer.value.chapters).find((item) => item.id === chapterId) ||
    flatten(designer.value.chapters)[0];
  if (!chapter) return;
  selectedChapter.value = chapter;
  const block = chapter.blocks.find((item) => item.id === blockId);
  selectedBlock.value = block;
  expandedContentBlockId.value = block?.id;
  selectMapping(
    block?.mappings.find((item) => item.id === mappingId) || block?.mappings[0],
    false,
  );
}

async function loadAll() {
  loading.value = true;
  try {
    await Promise.all([
      loadDesigner(false),
      adminApi.sources().then((value) => {
        sources.value = value;
      }),
      adminApi.standardFields().then((value) => {
        standardFields.value = value;
      }),
      adminApi.versions().then((value) => {
        versions.value = value;
      }),
      adminApi.limsImports().then((value) => {
        limsImports.value = value;
      }),
    ]);
  } catch (error) {
    ElMessage.error(errorText(error));
  } finally {
    loading.value = false;
  }
  await nextTick();
  await openOnlyOffice();
}

async function refreshStandardFields() { try { standardFields.value = await adminApi.standardFields(selectedChapter.value?.id); } catch (error) { ElMessage.error(errorText(error)); } }

function generateMappingIdentifiers(mapping: Partial<MappingRule>) {
  return mappingIdentifiers(mapping, {
    chapters: designer.value ? flatten(designer.value.chapters) : [],
    selectedChapter: selectedChapter.value,
    selectedBlock: selectedBlock.value,
  });
}
function generateMappingDisplayName(mapping: Partial<MappingRule>) {
  return mappingDisplayName(mapping, {
    chapters: designer.value ? flatten(designer.value.chapters) : [],
    selectedChapter: selectedChapter.value,
    selectedBlock: selectedBlock.value,
  }, standardFields.value);
}
function requestPluginBind(mapping: MappingRule, tag: string, oldInternalId: string) {
  return requestWordBind(mapping.wordLabel, tag, oldInternalId);
}
async function bindCurrentWordPosition(mapping: MappingRule) {
  if (!hasConnector() && !pluginReady.value)
    return ElMessage.warning("Word 编辑器尚未连接完成");
  if (bindingMappingId.value) return;
  bindingMappingId.value = mapping.id;
  let created: Control | undefined;
  let createdNew = false;
  try {
    const identifiers = generateMappingIdentifiers(mapping);
    const tag = identifiers.controlTag;
    const oldControl = controls.value.find(
      (item) => controlTag(item) === mapping.controlTag,
    );
    let selectedText = "";
    let existing = false;
    if (hasConnector()) {
      selectedText = String(
        (await execWord("GetSelectedText", [
          { Numbering: false, Math: true, ParaSeparator: "\n" },
        ])) || "",
      ).trim();
      if (!selectedText)
        throw new Error("请先在 Word 中选中要绑定的文字，再点击此按钮");
      const current = (await execWord("GetCurrentContentControlPr")) as Control | null;
      if (current && controlTag(current) === mapping.controlTag) existing = true;
      else if (current && controlId(current))
        throw new Error("当前文字已属于其他内容控件，请改选未绑定的文字");
      if (existing) created = current || undefined;
      else {
        created = (await execWord("AddContentControl", [
          1,
          { Tag: tag, Alias: mapping.wordLabel, Lock: 3, Appearance: 1,
            Color: { R: 33, G: 122, B: 103 } },
        ])) as Control | undefined;
        createdNew = true;
      }
    } else {
      const result = await requestPluginBind(mapping, tag, controlId(oldControl));
      created = result.control;
      selectedText = result.selectedText;
      existing = result.existing;
      createdNew = !existing;
    }
    if (!created || controlTag(created) !== tag)
      throw new Error("Word 未能为当前选区创建内容控件，请重新选择文字后再试");

    const updated = await adminApi.updateMapping(mapping.id, {
      fieldCode: identifiers.fieldCode,
      controlTag: tag,
      locationId: identifiers.locationId,
    });
    // 绑定成功后同步当前编辑草稿，避免随后点击“保存字段配置”用旧的空标签覆盖绑定。
    if (mappingDraft.value?.id === mapping.id) {
      mappingDraft.value.controlTag = updated.controlTag;
      mappingDraft.value.locationId = updated.locationId;
      mappingDraft.value.fieldCode = updated.fieldCode;
    }
    if (oldControl && controlId(oldControl) !== controlId(created)) {
      if (hasConnector()) await execWord("RemoveContentControl", [controlId(oldControl)]);
      else await requestPluginUnbind(controlId(oldControl));
    }

    if (hasConnector()) await refreshWordControls();
    await adminApi.forceSaveOnlyOffice();
    await loadDesigner(true);
    const refreshed = flatten(designer.value?.chapters || [])
      .flatMap((chapter) => chapter.blocks)
      .flatMap((block) => block.mappings)
      .find((item) => item.id === updated.id);
    if (refreshed) selectMapping(refreshed, false);
    await locateInWord(tag);
    ElMessage.success(
      existing ? "该文字已经绑定到当前字段" : `已绑定“${selectedText.slice(0, 30)}”并保存`,
    );
  } catch (error) {
    if (createdNew && created && controlId(created)) {
      try {
        if (hasConnector()) await execWord("RemoveContentControl", [controlId(created)]);
        else await requestPluginUnbind(controlId(created));
      } catch { /* Preserve the original failure; the new control can be removed manually. */ }
    }
    ElMessage.error(errorText(error));
  } finally {
    bindingMappingId.value = undefined;
  }
}
async function unbindCurrentWordPosition() {
  if (!hasConnector() && !pluginReady.value)
    return ElMessage.warning("Word 编辑器尚未连接完成");
  if (unbindingWord.value) return;
  try {
    await ElMessageBox.confirm(
      "解除当前文字的 Word 绑定？原文字和样式会保留，之后可以重新绑定。",
      "解除 Word 绑定",
      { type: "warning", confirmButtonText: "解除绑定", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  unbindingWord.value = true;
  try {
    if (hasConnector()) {
      const current = (await execWord("GetCurrentContentControlPr")) as Control | null;
      const id = controlId(current);
      if (!id) throw new Error("请先在 Word 中点击要解除绑定的文字");
      await execWord("RemoveContentControl", [id]);
      await refreshWordControls();
    } else {
      await requestPluginUnbind();
    }
    if (selectedMapping.value) {
      await adminApi.updateMapping(selectedMapping.value.id, { controlTag: '', locationId: '' });
      await loadDesigner(true);
    }
    ElMessage.success("已解除 Word 绑定，原文字和样式已保留");
  } catch (error) {
    ElMessage.error(errorText(error));
  } finally {
    unbindingWord.value = false;
  }
}
function handleWordTag(tag: string) {
  const all = designer.value ? flatten(designer.value.chapters) : [];
  const target = all
    .flatMap((chapter) => chapter.blocks.map((block) => ({ chapter, block })))
    .find((item) => item.block.controlTags.includes(tag));
  if (!target) return;
  selectBlock(target.chapter, target.block, false);
  selectMapping(
    target.block.mappings.find((item) => item.controlTag === tag),
    false,
  );
}
async function changeWorkspace(mode: WorkspaceMode) {
  if (mode !== "designer") {
    closeOnlyOffice();
  }
  workspaceMode.value = mode;
  if (mode === "designer") {
    await nextTick();
    await openOnlyOffice();
  }
}

onMounted(() => {
  void loadAll();
});
</script>

<template>
  <div class="template-admin" v-loading="loading">
    <AdminDesignerHeader
      :workspace="workspaceMode"
      :template-name="designer?.template.name"
      :published-version="designer?.template.publishedVersion"
      :user-name="sessionUser.displayName"
      :validating="validating"
      :publishing="publishing"
      @workspace="changeWorkspace"
      @validate="validateRules"
      @publish="publishRules"
      @back="$emit('back')"
      @logout="$emit('logout')"
    />

    <main v-if="workspaceMode === 'designer'" class="designer-workspace">
      <AdminChapterTree
        v-model:search="search"
        :chapters="filteredChapters"
        :selected-chapter-id="selectedChapter?.id"
        :selected-block-id="selectedBlock?.id"
        :expanded="expanded"
        :mappings="designer?.summary.mappings || 0"
        :pending="designer?.summary.pending || 0"
        @refresh="loadDesigner(true)"
        @edit-chapter="editChapter"
        @remove-chapter="removeChapter"
        @select-chapter="selectChapter"
        @select-block="selectBlock"
      />
      <AdminWordCanvas
        :chapter-label="selectedChapter ? codeTitle(selectedChapter) : '请选择章节'"
        :block-title="selectedBlock?.title || '本章节全部内容'"
        :link-state="wordLinkState"
        :loading="onlyOfficeLoading"
        :error="onlyOfficeError"
        :mapping="selectedMapping"
        @reload="openOnlyOffice"
      />
      <AdminInspectorPanel
        v-model:selected-chapter="selectedChapter"
        v-model:mapping-draft="mappingDraft"
        v-model:advanced-open="advancedOpen"
        v-model:drag-over-block-id="dragOverBlockId"
        v-model:drag-over-mapping-id="dragOverMappingId"
        :selected-block="selectedBlock"
        :selected-mapping="selectedMapping"
        :expanded-content-block-id="expandedContentBlockId"
        :dragging-block-id="draggingBlockId"
        :dragging-mapping-id="draggingMappingId"
        :binding-mapping-id="bindingMappingId"
        :unbinding-word="unbindingWord"
        :saving="saving"
        :standard-fields="standardFields"
        :calculation-field-options="calculationFieldOptions"
        @edit-block="editBlock"
        @start-block-drag="startBlockDrag"
        @finish-drag="finishDrag"
        @toggle-block="toggleContentBlock"
        @add-mapping="addMapping"
        @remove-block="removeBlock"
        @drop-block="dropBlock"
        @select-block="selectBlock"
        @select-mapping="selectMapping"
        @refresh-standard-fields="refreshStandardFields"
        @start-mapping-drag="startMappingDrag"
        @drop-mapping="dropMapping"
        @bind-mapping="bindCurrentWordPosition"
        @remove-mapping="removeMapping"
        @unbind="unbindCurrentWordPosition"
        @source-type-change="onSourceTypeChange"
        @select-standard-field="selectStandardField"
        @calculation-function="insertCalculationFunction"
        @calculation-reference="insertCalculationReference"
        @save-mapping="saveMapping"
      />
    </main>

    <AdminSourcesView v-else-if="workspaceMode === 'sources'" :sources="sources" :lims-imports="limsImports"
      @configure="editSource" @recognize="openRecognition" />
    <AdminVersionsView v-else :versions="versions" @publish="publishRules" />

    <AdminStructureDialogs
      v-model:chapter-open="chapterDialog"
      v-model:block-open="blockDialog"
      v-model:chapter="chapterDraft"
      v-model:block="blockDraft"
      :block-kind-options="blockKindOptions"
      :saving="saving"
      @save-chapter="saveChapter"
      @save-block="saveBlock"
      @detect-table="detectCurrentTable"
    />
    <AdminSourceDialogs
      v-model:source-open="sourceDialog"
      v-model:source="sourceDraft"
      v-model:source-config="sourceConfigText"
      v-model:recognition-open="recognitionDialog"
      v-model:recognition-result-open="recognitionResultDialog"
      v-model:recognition-import="recognitionImport"
      v-model:recognition-ids="recognitionIds"
      :lims-imports="limsImports"
      :testing="recognitionTesting"
      :result="recognitionResult"
      @save-source="saveSource"
      @recognize="runRecognition"
    />
    <AdminValidationDialog v-model:open="validationDialog" :validation="validation" />
  </div>
</template>

<style scoped>
.template-admin {
  height: 100vh;
  min-width: 1180px;
  color: #263731;
  background: #f4f7fb;
  overflow: hidden;
}
.designer-workspace {
  height: calc(100vh - 64px);
  display: grid;
  grid-template-columns:
    minmax(300px, 1fr)
    minmax(580px, 980px)
    minmax(400px, 1.1fr);
  overflow: hidden;
}
@media (max-width: 1280px) {
  .designer-workspace {
    grid-template-columns: 300px minmax(480px, 1fr) 400px;
  }
  .template-switcher > span {
    display: none;
  }
  .header-modes button {
    padding: 0 8px;
  }
}
</style>
