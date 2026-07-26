<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import {
  ArrowLeft,
  Check,
  Connection,
  Delete,
  DocumentChecked,
  EditPen,
  Files,
  Plus,
  Rank,
  Refresh,
  Search,
  Setting,
  SwitchButton,
  Tickets,
  Link,
  Unlock,
  Warning,
} from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
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
import StandardFieldPicker from "./StandardFieldPicker.vue";
import type { AuthUser } from "./auth-api";

defineProps<{
  catalogTemplate?: AdminTemplate;
  catalogVersion?: AdminTemplateVersion;
  sessionUser: AuthUser;
}>();
defineEmits<{ back: []; logout: [] }>();
type WorkspaceMode = "designer" | "sources" | "versions";
type Connector = {
  executeMethod?: (
    name: string,
    args: unknown[],
    callback?: (result: unknown) => void,
  ) => void;
  disconnect?: () => void;
};
type Editor = { destroyEditor?: () => void; createConnector?: () => Connector };
type Control = {
  Tag?: string;
  tag?: string;
  InternalId?: string;
  internalId?: string;
  Id?: string;
  id?: string;
};

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
const draggingBlockId = ref<number>();
const dragOverBlockId = ref<number>();
const draggingMappingId = ref<number>();
const dragOverMappingId = ref<number>();
const reordering = ref(false);
const mappingDraft = ref<Partial<MappingRule>>();
const chapterDraft = ref<Partial<DesignerChapter>>({});
const chapterDialog = ref(false);
const blockDialog = ref(false);
const blockDraft = ref<Partial<DesignerBlock>>();
const advancedOpen = ref(false);
const saving = ref(false);
const sourceDialog = ref(false);
const sourceDraft = ref<DataSourceRule>();
const sourceConfigText = ref("{}");
const recognitionDialog = ref(false);
const recognitionResultDialog = ref(false);
const recognitionImport = ref<LimsImport>();
const recognitionIds = ref<string[]>([]);
const recognitionTesting = ref(false);
const recognitionResult = ref<LimsRecognitionTest>();
const validation = ref<ValidationReport>();
const validationDialog = ref(false);
const validating = ref(false);
const publishing = ref(false);
const wordReady = ref(false);
const onlyOfficeLoading = ref(false);
const onlyOfficeError = ref("");
const wordLinkState = ref<"CONNECTING" | "READY" | "LIMITED">("CONNECTING");
const pendingLocateTag = ref<string>();
const controls = ref<Control[]>([]);
const bindingMappingId = ref<number>();
const unbindingWord = ref(false);
const pluginReady = ref(false);
const pendingWordCommands = new Map<
  number,
  {
    resolve: (value: { control: Control; selectedText: string; existing: boolean }) => void;
    reject: (reason: Error) => void;
    timer: number;
  }
>();
const pendingUnbindCommands = new Map<
  number,
  { resolve: () => void; reject: (reason: Error) => void; timer: number }
>();
let editor: Editor | undefined;
let connector: Connector | undefined;
let selectionTimer: number | undefined;

declare global {
  interface Window {
    __reportTemplateLinkCommand?: {
      type: "select";
      tag?: string;
      id?: string;
      nonce: number;
    };
  }
}

const sourceLabels: Record<string, string> = {
  FIXED: "模板固定内容",
  LIMS: "LIMS 数据",
  PDF: "PDF 文档",
  AI: "大模型生成",
  CALCULATED: "系统计算",
  MANUAL: "人工录入",
};
const dataTypeOptions = [
  { value: "string", label: "文本" },
  { value: "decimal", label: "数值" },
  { value: "date", label: "日期" },
  { value: "richText", label: "富文本" },
  { value: "formula", label: "计算公式" },
  { value: "image", label: "图片" },
];
const fillRuleOptions = [
  { value: "TEXT", label: "按普通文本填充" },
  { value: "PRESERVE_STYLE;EMPTY_AS_DASH", label: "保留样式，空值填短横线" },
  { value: "VERSION_2_DIGITS", label: "格式化为两位版本号" },
  { value: "WORD_FIELD", label: "保留为文档域" },
];
const mergeRuleOptions = [
  { value: "PRESERVE", label: "保留模板原有结构" },
  { value: "VERTICAL_BY_VALUE", label: "相同值纵向合并" },
];
const blockKindOptions: Array<{ value: ContentBlockKind; label: string }> = [
  { value: "FIXED", label: "固定内容" },
  { value: "MAPPED_FIELD", label: "单值字段组" },
  { value: "REPEATING_TABLE", label: "循环表格" },
  { value: "MATRIX", label: "结果矩阵" },
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
function errorText(error: unknown) {
  const value = error as {
    response?: { data?: { detail?: string | { message?: string } } };
    message?: string;
  };
  const detail = value.response?.data?.detail;
  return typeof detail === "string"
    ? detail
    : detail?.message || value.message || "操作失败";
}
function sourceTagType(type: string) {
  return (
    (
      {
        LIMS: "success",
        PDF: "warning",
        CALCULATED: "primary",
        AI: "danger",
        FIXED: "info",
      } as Record<string, string>
    )[type] || "info"
  );
}
function blockTone(block: DesignerBlock) {
  return block.status === "DISABLED"
    ? "disabled"
    : block.status === "PENDING"
      ? "pending"
      : block.kind.toLowerCase();
}
function codeTitle(item: DesignerChapter) {
  return ["cover", "headerFooter"].includes(item.code)
    ? item.title
    : `${item.code}. ${item.title}`;
}

function firstAnchoredMapping(
  chapter: DesignerChapter,
): MappingRule | undefined {
  const own = chapter.blocks.flatMap((block) => block.mappings);
  return (
    own.find((mapping) => mapping.controlTag) ||
    chapter.children.map(firstAnchoredMapping).find(Boolean)
  );
}
function selectChapter(chapter: DesignerChapter) {
  selectedChapter.value = chapter;
  const ownMappings = chapter.blocks.flatMap((block) => block.mappings);
  const ownTarget =
    ownMappings.find((mapping) => mapping.controlTag) || ownMappings[0];
  selectedBlock.value =
    chapter.blocks.find((block) =>
      block.mappings.some((mapping) => mapping.id === ownTarget?.id),
    ) || chapter.blocks[0];
  expandedContentBlockId.value = selectedBlock.value?.id;
  selectMapping(ownTarget, Boolean(ownTarget?.controlTag));
  if (!ownTarget?.controlTag) {
    const descendantTarget = firstAnchoredMapping(chapter);
    if (descendantTarget?.controlTag)
      void locateInWord(descendantTarget.controlTag);
  }
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
function moveByDrop<T extends { id: number }>(
  items: T[],
  sourceId: number,
  targetId: number,
  after: boolean,
) {
  const source = items.find((item) => item.id === sourceId);
  if (!source || sourceId === targetId) return items;
  const result = items.filter((item) => item.id !== sourceId);
  const targetIndex = result.findIndex((item) => item.id === targetId);
  result.splice(targetIndex + (after ? 1 : 0), 0, source);
  return result;
}
function dropAfter(event: DragEvent) {
  const target = event.currentTarget as HTMLElement | null;
  if (!target) return false;
  const bounds = target.getBoundingClientRect();
  return event.clientY > bounds.top + bounds.height / 2;
}
function startBlockDrag(event: DragEvent, block: DesignerBlock) {
  draggingBlockId.value = block.id;
  event.dataTransfer?.setData("text/plain", `block:${block.id}`);
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
}
async function dropBlock(event: DragEvent, target: DesignerBlock) {
  event.preventDefault();
  const chapter = selectedChapter.value;
  const sourceId = draggingBlockId.value;
  if (!chapter || !sourceId || reordering.value) return;
  const ordered = moveByDrop(chapter.blocks, sourceId, target.id, dropAfter(event));
  if (ordered === chapter.blocks) return;
  ordered.forEach((item, orderNo) => {
    item.orderNo = orderNo;
  });
  chapter.blocks = ordered;
  reordering.value = true;
  try {
    await adminApi.reorderContentBlocks(
      chapter.id,
      chapter.blocks.map((item) => item.id),
    );
    ElMessage.success("内容块顺序已保存");
  } catch (error) {
    await loadDesigner(true);
    ElMessage.error(errorText(error));
  } finally {
    draggingBlockId.value = undefined;
    dragOverBlockId.value = undefined;
    reordering.value = false;
  }
}
function startMappingDrag(event: DragEvent, mapping: MappingRule) {
  draggingMappingId.value = mapping.id;
  event.dataTransfer?.setData("text/plain", `mapping:${mapping.id}`);
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
}
async function dropMapping(event: DragEvent, block: DesignerBlock, target: MappingRule) {
  event.preventDefault();
  event.stopPropagation();
  const sourceId = draggingMappingId.value;
  if (!sourceId || reordering.value) return;
  const ordered = moveByDrop(block.mappings, sourceId, target.id, dropAfter(event));
  if (ordered === block.mappings) return;
  block.mappings = ordered;
  block.mappingIds = ordered.map((item) => item.id);
  reordering.value = true;
  try {
    await adminApi.reorderBlockMappings(block.id, block.mappingIds);
    ElMessage.success("字段顺序已保存");
  } catch (error) {
    await loadDesigner(true);
    ElMessage.error(errorText(error));
  } finally {
    draggingMappingId.value = undefined;
    dragOverMappingId.value = undefined;
    reordering.value = false;
  }
}
function finishDrag() {
  draggingBlockId.value = undefined;
  dragOverBlockId.value = undefined;
  draggingMappingId.value = undefined;
  dragOverMappingId.value = undefined;
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
  designer.value = await adminApi.designer();
  expanded.value = flatten(designer.value.chapters).map((item) => item.id);
  const chapter =
    flatten(designer.value.chapters).find((item) => item.id === chapterId) ||
    flatten(designer.value.chapters)[0];
  if (!chapter) return;
  selectedChapter.value = chapter;
  const block =
    chapter.blocks.find((item) => item.id === blockId) || chapter.blocks[0];
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

function loadOnlyOfficeApi(serverUrl: string) {
  if (window.DocsAPI) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      "script[data-onlyoffice-api]",
    );
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error("ONLYOFFICE 编辑器脚本加载失败")),
        { once: true },
      );
      return;
    }
    const script = document.createElement("script");
    script.src = `${serverUrl}/web-apps/apps/api/documents/api.js`;
    script.dataset.onlyofficeApi = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("ONLYOFFICE 编辑器脚本加载失败"));
    document.head.appendChild(script);
  });
}
function execWord(name: string, args: unknown[] = []) {
  return new Promise<unknown>((resolve) => {
    if (!connector?.executeMethod) return resolve(undefined);
    try {
      connector.executeMethod(name, args, (result) => resolve(result));
    } catch {
      resolve(undefined);
    }
  });
}
function controlTag(control?: Control | null) {
  return control?.Tag || control?.tag || "";
}
function controlId(control?: Control | null) {
  return (
    control?.InternalId || control?.internalId || control?.Id || control?.id || ""
  );
}
function identifierSegment(value: string, fallback: string, maxLength = 48) {
  const normalized = value
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "_")
    .replace(/^_+|_+$/g, "");
  return (normalized || fallback).slice(0, maxLength);
}
function isTemporaryIdentifier(value?: string) {
  const current = (value || "").trim();
  return (
    !current ||
    /^\d+$/.test(current) ||
    current.startsWith("draft.") ||
    /^(?:word\.)?contentcontrol\.\d+$/i.test(current) ||
    /^report\..+\.mapping\.\d+$/.test(current)
  );
}
function mappingContext(mapping: Partial<MappingRule>) {
  const chapters = designer.value ? flatten(designer.value.chapters) : [];
  const chapter =
    chapters.find((item) => item.id === mapping.chapterId) ||
    chapters.find((item) => item.code === mapping.sectionCode) ||
    selectedChapter.value;
  const block =
    chapter?.blocks.find((item) => item.id === mapping.blockId) ||
    chapter?.blocks.find((item) =>
      item.mappings.some((field) => field.id === mapping.id),
    ) ||
    selectedBlock.value;
  return { chapter, block };
}
function generateMappingIdentifiers(mapping: Partial<MappingRule>) {
  const { chapter, block } = mappingContext(mapping);
  const rawSection = mapping.sectionCode || chapter?.code || "field";
  const section = ["cover", "headerFooter"].includes(rawSection)
    ? identifierSegment(rawSection, "field")
    : `s${identifierSegment(rawSection, "field")}`;
  const field = identifierSegment(mapping.wordLabel || "", `field_${mapping.id || "new"}`);
  const blockName = identifierSegment(block?.title || "", "");
  const parts = ["report", section];
  if (blockName && blockName !== field) parts.push(blockName);
  parts.push(field);

  let generatedFieldCode = parts.join(".");
  const allMappings = (designer.value?.chapters ? flatten(designer.value.chapters) : [])
    .flatMap((item) => item.blocks)
    .flatMap((item) => item.mappings)
    .filter((item) => item.id !== mapping.id);
  if (allMappings.some((item) => item.fieldCode === generatedFieldCode))
    generatedFieldCode += `.m${mapping.id || Date.now()}`;

  const fieldCode = isTemporaryIdentifier(mapping.fieldCode)
    ? generatedFieldCode
    : String(mapping.fieldCode);
  let generatedTag = `cc.${fieldCode}`;
  if (allMappings.some((item) => item.controlTag === generatedTag))
    generatedTag += `.m${mapping.id || Date.now()}`;
  const controlTag = isTemporaryIdentifier(mapping.controlTag)
    ? generatedTag
    : String(mapping.controlTag);
  return {
    fieldCode,
    controlTag,
    locationId: `word.content_control.${controlTag}`,
  };
}
function generateMappingDisplayName(mapping: Partial<MappingRule>) {
  const current = String(mapping.wordLabel || "").trim();
  if (current && current !== "新字段") return current;
  const standard = standardFields.value.find(
    (item) => item.fieldCode === mapping.standardFieldCode,
  );
  if (standard?.label) return standard.label;
  const { block } = mappingContext(mapping);
  return block?.title ? `${block.title}字段` : "未命名字段";
}
function requestPluginBind(mapping: MappingRule, tag: string, oldInternalId: string) {
  const nonce = Date.now();
  return new Promise<{ control: Control; selectedText: string; existing: boolean }>(
    (resolve, reject) => {
      const timer = window.setTimeout(() => {
        pendingWordCommands.delete(nonce);
        reject(new Error("Word 绑定响应超时，请确认编辑器已加载后重试"));
      }, 12000);
      pendingWordCommands.set(nonce, { resolve, reject, timer });
      adminApi
        .sendWordCommand({
          type: "bind",
          nonce,
          tag,
          alias: mapping.wordLabel,
          oldInternalId,
        })
        .catch((error) => {
          window.clearTimeout(timer);
          pendingWordCommands.delete(nonce);
          reject(error instanceof Error ? error : new Error(errorText(error)));
        });
    },
  );
}
function requestPluginUnbind() {
  const nonce = Date.now();
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      pendingUnbindCommands.delete(nonce);
      reject(new Error("Word 解除绑定响应超时，请确认编辑器已加载后重试"));
    }, 12000);
    pendingUnbindCommands.set(nonce, { resolve, reject, timer });
    adminApi.sendWordCommand({ type: "unbind", nonce }).catch((error) => {
      window.clearTimeout(timer);
      pendingUnbindCommands.delete(nonce);
      reject(error instanceof Error ? error : new Error(errorText(error)));
    });
  });
}
async function refreshWordControls() {
  const result = await execWord("GetAllContentControls");
  controls.value = Array.isArray(result) ? (result as Control[]) : [];
  wordLinkState.value = controls.value.length ? "READY" : "LIMITED";
}
async function bindCurrentWordPosition(mapping: MappingRule) {
  if (!connector?.executeMethod && !pluginReady.value)
    return ElMessage.warning("Word 编辑器尚未连接完成");
  if (bindingMappingId.value) return;

  bindingMappingId.value = mapping.id;
  let created: Control | undefined;
  try {
    const identifiers = generateMappingIdentifiers(mapping);
    const tag = identifiers.controlTag;
    const oldControl = controls.value.find(
      (item) => controlTag(item) === mapping.controlTag,
    );
    let selectedText = "";
    let existing = false;
    if (connector?.executeMethod) {
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
          2,
          { Tag: tag, Alias: mapping.wordLabel, Lock: 3, Appearance: 1,
            Color: { R: 33, G: 122, B: 103 } },
        ])) as Control | undefined;
      }
    } else {
      const result = await requestPluginBind(mapping, tag, controlId(oldControl));
      created = result.control;
      selectedText = result.selectedText;
      existing = result.existing;
    }
    if (!created || controlTag(created) !== tag)
      throw new Error("Word 未能为当前选区创建内容控件，请重新选择文字后再试");

    const updated = await adminApi.updateMapping(mapping.id, {
      fieldCode: identifiers.fieldCode,
      controlTag: tag,
      locationId: identifiers.locationId,
    });
    if (connector?.executeMethod && oldControl && controlId(oldControl) !== controlId(created))
      await execWord("RemoveContentControl", [controlId(oldControl)]);

    if (connector?.executeMethod) await refreshWordControls();
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
    if (created && controlId(created))
      await execWord("RemoveContentControl", [controlId(created)]);
    ElMessage.error(errorText(error));
  } finally {
    bindingMappingId.value = undefined;
  }
}
async function unbindCurrentWordPosition() {
  if (!connector?.executeMethod && !pluginReady.value)
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
    if (connector?.executeMethod) {
      const current = (await execWord("GetCurrentContentControlPr")) as Control | null;
      const id = controlId(current);
      if (!id) throw new Error("请先在 Word 中点击要解除绑定的文字");
      await execWord("RemoveContentControl", [id]);
      await refreshWordControls();
    } else {
      await requestPluginUnbind();
    }
    ElMessage.success("已解除 Word 绑定，原文字和样式已保留");
  } catch (error) {
    ElMessage.error(errorText(error));
  } finally {
    unbindingWord.value = false;
  }
}
async function connectWord() {
  connector?.disconnect?.();
  connector = editor?.createConnector?.();
  if (!connector?.executeMethod) {
    wordLinkState.value = "LIMITED";
    return;
  }
  await refreshWordControls();
  if (selectionTimer) window.clearInterval(selectionTimer);
  selectionTimer = window.setInterval(async () => {
    const current = (await execWord("GetCurrentContentControlPr")) as
      | Control
      | undefined;
    const tag = controlTag(current);
    if (tag) handleWordTag(tag);
  }, 700);
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
function onWordMessage(event: MessageEvent) {
  const message = event.data as {
    source?: string;
    type?: string;
    data?: unknown;
  };
  if (message?.source !== "report-template-link") return;
  if (message.type === "controls" && Array.isArray(message.data)) {
    pluginReady.value = true;
    controls.value = message.data as Control[];
    wordLinkState.value = controls.value.length ? "READY" : "LIMITED";
    // Some local Document Server builds start the autostart plugin before
    // emitting DocsAPI.onDocumentReady. The plugin message proves that Word is
    // ready, so establish the connector here as a version-compatible fallback.
    wordReady.value = true;
    if (editor?.createConnector && !connector?.executeMethod) void connectWord();
  } else if (message.type === "selection" && message.data) {
    const tag = controlTag(message.data as Control);
    if (tag) handleWordTag(tag);
  } else if ((message.type === "bind-result" || message.type === "bind-error") && message.data) {
    const result = message.data as {
      nonce: number;
      message?: string;
      control?: Control;
      selectedText?: string;
      existing?: boolean;
    };
    const pending = pendingWordCommands.get(result.nonce);
    if (!pending) return;
    window.clearTimeout(pending.timer);
    pendingWordCommands.delete(result.nonce);
    if (message.type === "bind-error") pending.reject(new Error(result.message || "Word 绑定失败"));
    else pending.resolve({
      control: result.control || {},
      selectedText: result.selectedText || "",
      existing: Boolean(result.existing),
    });
  } else if ((message.type === "unbind-result" || message.type === "unbind-error") && message.data) {
    const result = message.data as { nonce: number; message?: string };
    const pending = pendingUnbindCommands.get(result.nonce);
    if (!pending) return;
    window.clearTimeout(pending.timer);
    pendingUnbindCommands.delete(result.nonce);
    if (message.type === "unbind-error")
      pending.reject(new Error(result.message || "解除 Word 绑定失败"));
    else pending.resolve();
  }
}
async function openOnlyOffice() {
  if (workspaceMode.value !== "designer") return;
  onlyOfficeLoading.value = true;
  onlyOfficeError.value = "";
  wordReady.value = false;
  wordLinkState.value = "CONNECTING";
  try {
    editor?.destroyEditor?.();
    const bootstrap = await adminApi.onlyOfficeConfig();
    await loadOnlyOfficeApi(bootstrap.documentServerUrl);
    await nextTick();
    if (!window.DocsAPI) throw new Error("ONLYOFFICE 编辑器 API 不可用");
    bootstrap.config.events = {
      onDocumentReady: async () => {
        wordReady.value = true;
        await connectWord();
        const tag = pendingLocateTag.value;
        if (tag) await locateInWord(tag);
      },
      onError: (event: unknown) => {
        onlyOfficeError.value = `模板编辑器发生错误：${JSON.stringify(event)}`;
      },
    };
    editor = new window.DocsAPI.DocEditor(
      "admin-onlyoffice-editor",
      bootstrap.config,
    ) as Editor;
  } catch (error) {
    onlyOfficeError.value = errorText(error);
  } finally {
    onlyOfficeLoading.value = false;
  }
}
async function locateInWord(tag?: string) {
  if (!tag) return;
  const control = controls.value.find((item) => controlTag(item) === tag);
  const id = controlId(control);
  window.__reportTemplateLinkCommand = {
    type: "select",
    tag,
    id,
    nonce: Date.now(),
  };
  if (!wordReady.value) {
    pendingLocateTag.value = tag;
    return;
  }
  pendingLocateTag.value = undefined;
  if (id) {
    await execWord("SelectContentControl", [id]);
    await execWord("MoveCursorToContentControl", [id, false]);
  }
}
async function changeWorkspace(mode: WorkspaceMode) {
  if (mode !== "designer") {
    if (selectionTimer) window.clearInterval(selectionTimer);
    connector?.disconnect?.();
    editor?.destroyEditor?.();
    connector = undefined;
    editor = undefined;
    wordReady.value = false;
  }
  workspaceMode.value = mode;
  if (mode === "designer") {
    await nextTick();
    await openOnlyOffice();
  }
}

function editChapter(chapter?: DesignerChapter, parent?: DesignerChapter) {
  chapterDraft.value = chapter
    ? JSON.parse(JSON.stringify(chapter))
    : {
        parentId: parent?.id,
        code: "",
        title: "",
        pageHint: undefined,
        orderNo: (designer.value?.summary.chapters || 0) + 1,
        enabled: true,
      };
  chapterDialog.value = true;
}
async function saveChapter() {
  if (!chapterDraft.value?.code || !chapterDraft.value.title)
    return ElMessage.warning("章节编号和名称不能为空");
  try {
    if (chapterDraft.value.id)
      await adminApi.updateChapter(chapterDraft.value.id, chapterDraft.value);
    else await adminApi.createChapter(chapterDraft.value);
    chapterDialog.value = false;
    await loadDesigner(true);
    ElMessage.success("章节目录已保存");
  } catch (error) {
    ElMessage.error(errorText(error));
  }
}
async function saveChapterFromInspector() {
  if (!selectedChapter.value) return;
  saving.value = true;
  try {
    await adminApi.updateChapter(
      selectedChapter.value.id,
      selectedChapter.value,
    );
    await loadDesigner(true);
    ElMessage.success("章节属性已保存");
  } catch (error) {
    ElMessage.error(errorText(error));
  } finally {
    saving.value = false;
  }
}
async function removeChapter(chapter: DesignerChapter) {
  try {
    await ElMessageBox.confirm(
      `删除“${codeTitle(chapter)}”？子章节会一并删除，字段将暂时变为未归类。`,
      "删除章节",
      { type: "warning" },
    );
    await adminApi.deleteChapter(chapter.id);
    await loadDesigner(false);
    ElMessage.success("章节已删除");
  } catch (error) {
    if (error !== "cancel" && error !== "close")
      ElMessage.error(errorText(error));
  }
}
function editBlock(block?: DesignerBlock) {
  if (!selectedChapter.value) return;
  blockDraft.value = block
    ? JSON.parse(JSON.stringify(block))
    : {
        chapterId: selectedChapter.value.id,
        title: "新内容块",
        kind: "MAPPED_FIELD",
        tableNo: "",
        sourcePath: "",
        repeatKey: "",
        prototypeLocation: "",
        dedupKey: "",
        sortRule: "",
        emptyBehavior: "KEEP",
        mergeRule: "NONE",
        orderNo: selectedChapter.value.blocks.length,
        enabled: true,
      };
  blockDialog.value = true;
}
async function saveBlock() {
  if (!blockDraft.value?.title?.trim())
    return ElMessage.warning("内容块名称不能为空");
  const repeating = ["REPEATING_TABLE", "MATRIX"].includes(
    blockDraft.value.kind || "",
  );
  if (repeating && !blockDraft.value.sourcePath?.trim())
    return ElMessage.warning("循环表格必须设置数据集合");
  saving.value = true;
  try {
    const saved = blockDraft.value.id
      ? await adminApi.updateContentBlock(blockDraft.value.id, blockDraft.value)
      : await adminApi.createContentBlock(blockDraft.value);
    blockDialog.value = false;
    await loadDesigner(true);
    const chapter = flatten(designer.value?.chapters || []).find(
      (item) => item.id === saved.chapterId,
    );
    const block = chapter?.blocks.find((item) => item.id === saved.id);
    if (chapter && block) selectBlock(chapter, block, false);
    ElMessage.success(blockDraft.value.id ? "内容块已保存" : "内容块已新增");
  } catch (error) {
    ElMessage.error(errorText(error));
  } finally {
    saving.value = false;
  }
}
async function removeBlock(block: DesignerBlock) {
  try {
    await ElMessageBox.confirm(
      `删除内容块“${block.title}”？块内 ${block.mappings.length} 个字段也会一并删除，但不会删除 Word 中的文字。`,
      "删除内容块",
      { type: "warning" },
    );
    await adminApi.deleteContentBlock(block.id, true);
    await loadDesigner(true);
    ElMessage.success("内容块及其字段已删除");
  } catch (error) {
    if (error !== "cancel" && error !== "close")
      ElMessage.error(errorText(error));
  }
}
function addMapping(block = selectedBlock.value) {
  if (!selectedChapter.value || !block)
    return ElMessage.warning("请先新增或选择一个内容块");
  selectedBlock.value = block;
  expandedContentBlockId.value = block.id;
  selectedMapping.value = undefined;
  mappingDraft.value = {
    chapterId: selectedChapter.value.id,
    blockId: block.id,
    locationId: `draft.block${block.id}.${Date.now()}`,
    sectionCode: selectedChapter.value.code,
    tableNo: block.tableNo || "TEXT",
    wordLabel: "新字段",
    fieldCode: "",
    dataType: "string",
    sourceType: "LIMS",
    sourcePath: "",
    repeatType: ["REPEATING_TABLE", "MATRIX"].includes(block.kind)
      ? "ROW"
      : "NONE",
    repeatKey: block.repeatKey || "",
    mergeRule: "PRESERVE",
    fillRule: "TEXT",
    calculationRule: "",
    calculationExpression: "",
    calculationDependencies: [],
    calculationScope: ["REPEATING_TABLE", "MATRIX"].includes(block.kind)
      ? "CURRENT_ROW"
      : "REPORT",
    calculationPrecision: 2,
    calculationNullBehavior: "ERROR",
    controlTag: "",
    required: false,
    sourcePending: true,
    enabled: true,
  };
}
function onSourceTypeChange(sourceType: string) {
  if (!mappingDraft.value) return;
  if (sourceType === "CALCULATED") {
    mappingDraft.value.sourcePath = "";
    mappingDraft.value.standardFieldCode = undefined;
    mappingDraft.value.dataType = "decimal";
    mappingDraft.value.calculationExpression ||= "";
    mappingDraft.value.calculationDependencies ||= [];
    mappingDraft.value.calculationScope ||= ["REPEATING_TABLE", "MATRIX"].includes(
      selectedBlock.value?.kind || "",
    )
      ? "CURRENT_ROW"
      : "REPORT";
    mappingDraft.value.calculationPrecision ??= 2;
    mappingDraft.value.calculationNullBehavior ||= "ERROR";
  }
}
function insertCalculationText(value: string) {
  if (!mappingDraft.value) return;
  const expression = mappingDraft.value.calculationExpression || "";
  mappingDraft.value.calculationExpression = `${expression}${expression ? " " : ""}${value}`;
}
function insertCalculationReference(code: string) {
  if (!mappingDraft.value) return;
  const dependencies = mappingDraft.value.calculationDependencies || [];
  if (!dependencies.includes(code)) {
    mappingDraft.value.calculationDependencies = [...dependencies, code];
  }
  insertCalculationText(`{${code}}`);
}
function insertCalculationFunction(name: string) {
  const snippets: Record<string, string> = {
    SUM: "SUM()",
    AVG: "AVG()",
    RSD: "RSD()",
    MIN: "MIN()",
    MAX: "MAX()",
    COUNT: "COUNT()",
    ABS: "ABS()",
    SQRT: "SQRT()",
    IF: 'IF(条件, "符合", "不符合")',
  };
  insertCalculationText(snippets[name]);
}
function selectStandardField(field: StandardField) {
  if (!mappingDraft.value) return;
  mappingDraft.value.standardFieldCode = field.fieldCode;
  mappingDraft.value.sourcePath = field.legacyJsonPath;
  mappingDraft.value.dataType = field.dataType;
}
async function saveMapping() {
  if (!mappingDraft.value) return;
  if (mappingDraft.value.sourceType === "CALCULATED") {
    const expression = mappingDraft.value.calculationExpression?.trim() || "";
    const dependencies = mappingDraft.value.calculationDependencies || [];
    if (!expression) return ElMessage.warning("请填写计算公式");
    if (!dependencies.length) return ElMessage.warning("请至少选择一个引用字段");
    const references = Array.from(
      expression.matchAll(/\{([^{}]+)\}/g),
      (match) => match[1].trim(),
    );
    const missing = references.filter((code) => !dependencies.includes(code));
    if (missing.length)
      return ElMessage.warning(`请先选择公式引用字段：${missing.join("、")}`);
  }
  const editingId = mappingDraft.value.id;
  mappingDraft.value.wordLabel = generateMappingDisplayName(mappingDraft.value);
  const identifiers = generateMappingIdentifiers(mappingDraft.value);
  mappingDraft.value.fieldCode = identifiers.fieldCode;
  mappingDraft.value.controlTag = identifiers.controlTag;
  mappingDraft.value.locationId = identifiers.locationId;
  saving.value = true;
  try {
    const saved = editingId
      ? await adminApi.updateMapping(editingId, mappingDraft.value)
      : await adminApi.createMapping(mappingDraft.value);
    await loadDesigner(true);
    const refreshedChapter = flatten(designer.value?.chapters || []).find(
      (item) => item.id === saved.chapterId,
    );
    const refreshedBlock = refreshedChapter?.blocks.find(
      (item) => item.id === saved.blockId,
    );
    const refreshedMapping = refreshedBlock?.mappings.find(
      (item) => item.id === saved.id,
    );
    if (refreshedChapter && refreshedBlock && refreshedMapping) {
      selectedChapter.value = refreshedChapter;
      selectedBlock.value = refreshedBlock;
      expandedContentBlockId.value = refreshedBlock.id;
      selectMapping(refreshedMapping, false);
    }
    ElMessage.success(
      editingId ? "字段修改已保存" : "字段映射已新增",
    );
  } catch (error) {
    ElMessage.error(errorText(error));
  } finally {
    saving.value = false;
  }
}
async function removeMapping(mapping: MappingRule) {
  try {
    await ElMessageBox.confirm(
      `删除字段“${mapping.wordLabel}”？不会删除 Word 中的文字。`,
      "删除字段映射",
      { type: "warning" },
    );
    await adminApi.deleteMapping(mapping.id);
    await loadDesigner(true);
    ElMessage.success("字段映射已删除");
  } catch (error) {
    if (error !== "cancel" && error !== "close")
      ElMessage.error(errorText(error));
  }
}
async function saveTableRule(table: TableRule) {
  saving.value = true;
  try {
    await adminApi.updateTable(table.tableNo, table);
    await loadDesigner(true);
    ElMessage.success("表格区域已保存");
  } catch (error) {
    ElMessage.error(errorText(error));
  } finally {
    saving.value = false;
  }
}
function editSource(item: DataSourceRule) {
  sourceDraft.value = JSON.parse(JSON.stringify(item));
  sourceConfigText.value = JSON.stringify(item.config, null, 2);
  sourceDialog.value = true;
}
async function saveSource() {
  if (!sourceDraft.value) return;
  try {
    sourceDraft.value.config = JSON.parse(sourceConfigText.value);
    await adminApi.updateSource(sourceDraft.value.code, sourceDraft.value);
    sources.value = await adminApi.sources();
    sourceDialog.value = false;
    ElMessage.success("数据源配置已保存");
  } catch (error) {
    ElMessage.error(
      error instanceof SyntaxError ? "配置必须是有效 JSON" : errorText(error),
    );
  }
}
async function validateRules() {
  validating.value = true;
  try {
    validation.value = await adminApi.validate();
    validationDialog.value = true;
  } catch (error) {
    ElMessage.error(errorText(error));
  } finally {
    validating.value = false;
  }
}
async function publishRules() {
  try {
    const result = await ElMessageBox.prompt(
      "请输入本次模板规则版本说明",
      "发布模板版本",
      {
        inputValue: "更新模板章节与字段规则",
        inputValidator: (value) => !!value || "请输入发布说明",
      },
    );
    publishing.value = true;
    const version = await adminApi.publish(result.value);
    versions.value = await adminApi.versions();
    await loadDesigner(true);
    ElMessage.success(`模板规则 V${version.versionNo} 已发布`);
  } catch (error) {
    if (error !== "cancel" && error !== "close")
      ElMessage.error(errorText(error));
  } finally {
    publishing.value = false;
  }
}
function openRecognition() {
  recognitionImport.value = limsImports.value[0];
  recognitionIds.value = [];
  recognitionDialog.value = true;
}
async function runRecognition() {
  if (!recognitionImport.value || !recognitionIds.value.length) return;
  recognitionTesting.value = true;
  try {
    recognitionResult.value = await adminApi.limsRecognition(
      recognitionImport.value.id,
      recognitionIds.value,
    );
    recognitionDialog.value = false;
    recognitionResultDialog.value = true;
  } catch (error) {
    ElMessage.error(errorText(error));
  } finally {
    recognitionTesting.value = false;
  }
}
function formatBytes(size: number) {
  return size < 1024 * 1024
    ? `${Math.round(size / 1024)} KB`
    : `${(size / 1024 / 1024).toFixed(1)} MB`;
}
onMounted(() => {
  window.addEventListener("message", onWordMessage);
  void loadAll();
});
onUnmounted(() => {
  window.removeEventListener("message", onWordMessage);
  if (selectionTimer) window.clearInterval(selectionTimer);
  connector?.disconnect?.();
  editor?.destroyEditor?.();
});
</script>

<template>
  <div class="template-admin" v-loading="loading">
    <el-button class="library-back" :icon="ArrowLeft" @click="$emit('back')"
      >模板库</el-button
    >
    <header class="designer-header">
      <div class="designer-brand">
        <Setting />
        <div>
          <strong>报告模板设计器</strong>
        </div>
      </div>
      <div class="template-switcher">
        <span>报告模板</span
        ><el-select model-value="primary-report-template" disabled
          ><el-option
            :label="designer?.template.name || '正在读取模板…'"
            value="primary-report-template" /></el-select
        ><el-tag type="warning" effect="plain">草稿</el-tag
        ><el-tag
          v-if="designer?.template.publishedVersion"
          type="success"
          effect="plain"
          >已发布 V{{ designer.template.publishedVersion }}</el-tag
        >
      </div>
      <nav class="header-modes">
        <button
          :class="{ active: workspaceMode === 'designer' }"
          @click="changeWorkspace('designer')"
        >
          <EditPen />模板设计</button
        ><button
          :class="{ active: workspaceMode === 'sources' }"
          @click="changeWorkspace('sources')"
        >
          <Connection />数据源</button
        ><button
          :class="{ active: workspaceMode === 'versions' }"
          @click="changeWorkspace('versions')"
        >
          <DocumentChecked />版本记录
        </button>
      </nav>
      <div class="header-actions">
        <el-button :icon="Check" :loading="validating" @click="validateRules"
          >校验</el-button
        ><el-button type="primary" :loading="publishing" @click="publishRules"
          >发布版本</el-button
        >
        <span class="designer-session-user">{{ sessionUser.displayName }}</span>
        <el-button :icon="SwitchButton" @click="$emit('logout')">退出</el-button>
      </div>
    </header>

    <main v-if="workspaceMode === 'designer'" class="designer-workspace">
      <aside class="chapter-panel">
        <div class="panel-title">
          <div>
            <strong>章节目录树</strong>
          </div>
          <div class="tree-actions">
            <el-button
              text
              :icon="Plus"
              aria-label="新增根章节"
              @click="editChapter()"
            /><el-button
              text
              :icon="Refresh"
              aria-label="刷新章节"
              @click="loadDesigner(true)"
            />
          </div>
        </div>
        <el-input
          v-model="search"
          class="chapter-search"
          :prefix-icon="Search"
          placeholder="搜索章节、字段或表格"
          clearable
        />
        <div class="coverage-line">
          <span
            ><i class="ready" />已配置
            {{
              (designer?.summary.mappings || 0) -
              (designer?.summary.pending || 0)
            }}</span
          ><span
            ><i class="pending" />待完善
            {{ designer?.summary.pending || 0 }}</span
          >
        </div>
        <div class="chapter-scroll">
          <section
            v-for="chapter in filteredChapters"
            :key="chapter.id"
            class="chapter-group"
          >
            <div
              class="chapter-row"
              :class="{ selected: selectedChapter?.id === chapter.id }"
            >
              <button @click="selectChapter(chapter)">
                <span>{{ codeTitle(chapter) }}</span
                ><small>{{ chapter.pageHint || "" }}</small>
              </button>
              <div class="tree-row-actions">
                <el-button
                  text
                  :icon="Plus"
                  aria-label="新增子章节"
                  @click="editChapter(undefined, chapter)"
                /><el-button
                  text
                  :icon="EditPen"
                  aria-label="编辑章节"
                  @click="editChapter(chapter)"
                /><el-button
                  text
                  :icon="Warning"
                  aria-label="删除章节"
                  @click="removeChapter(chapter)"
                />
              </div>
            </div>
            <div v-if="expanded.includes(chapter.id)" class="section-list">
              <div
                v-for="child in chapter.children"
                :key="child.id"
                class="section-group"
              >
                <div
                  class="section-row"
                  :class="{ selected: selectedChapter?.id === child.id }"
                >
                  <button @click="selectChapter(child)">
                    <span>{{ codeTitle(child) }}</span
                    ><small>{{ child.pageHint || "" }}</small>
                  </button>
                  <div class="tree-row-actions">
                    <el-button
                      text
                      :icon="EditPen"
                      aria-label="编辑章节"
                      @click="editChapter(child)"
                    /><el-button
                      text
                      :icon="Warning"
                      aria-label="删除章节"
                      @click="removeChapter(child)"
                    />
                  </div>
                </div>
                <button
                  v-for="block in child.blocks"
                  :key="block.id"
                  class="block-row"
                  :class="[
                    { selected: selectedBlock?.id === block.id },
                    blockTone(block),
                  ]"
                  @click="selectBlock(child, block)"
                >
                  <i /><span
                    ><b>{{ block.title }}</b></span
                  ><Warning v-if="block.status === 'PENDING'" />
                </button>
              </div>
            </div>
            <button
              v-for="block in chapter.blocks"
              :key="block.id"
              class="block-row"
              :class="[
                { selected: selectedBlock?.id === block.id },
                blockTone(block),
              ]"
              @click="selectBlock(chapter, block)"
            >
              <i /><span
                ><b>{{ block.title }}</b></span
              ><Warning v-if="block.status === 'PENDING'" />
            </button>
          </section>
          <div v-if="!filteredChapters.length" class="tree-empty">
            没有匹配的章节或字段
          </div>
        </div>
      </aside>
      <section class="word-panel">
        <div class="word-toolbar">
          <div class="breadcrumb">
            <span>{{
              selectedChapter ? codeTitle(selectedChapter) : "请选择章节"
            }}</span
            ><i>/</i><b>{{ selectedBlock?.title || "本章节全部内容" }}</b>
          </div>
          <div class="word-state" :class="wordLinkState.toLowerCase()">
            <i />{{
              wordLinkState === "READY"
                ? "Word 双向定位已连接"
                : wordLinkState === "LIMITED"
                  ? "Word 可编辑，定位能力受限"
                  : "正在连接 Word"
            }}
          </div>
        </div>
        <div class="word-canvas" v-loading="onlyOfficeLoading">
          <div id="admin-onlyoffice-editor" class="onlyoffice-editor" />
          <el-result
            v-if="onlyOfficeError"
            icon="error"
            title="模板编辑器加载失败"
            :sub-title="onlyOfficeError"
            ><template #extra
              ><el-button type="primary" @click="openOnlyOffice"
                >重新加载</el-button
              ></template
            ></el-result
          >
        </div>
        <footer class="word-footer">
          <b v-if="selectedMapping"
            ><Tickets />{{ selectedMapping.wordLabel }} ·
            {{ selectedMapping.controlTag || "锚点待建立" }}</b
          >
        </footer>
      </section>
      <aside class="inspector-panel">
        <div v-if="selectedChapter" class="inspector-head">
          <div class="inspector-path">
            模板目录 / {{ selectedChapter.code }}
          </div>
          <div class="inspector-title">
            <span class="kind-mark"><Files /></span>
            <div>
              <strong>{{ selectedChapter.title }}</strong>
            </div>
            <el-tag type="info" effect="plain">章节</el-tag>
          </div>
        </div>
        <div class="inspector-scroll">
          <el-form
            v-if="selectedChapter"
            label-position="top"
            class="inspector-form"
            ><div class="inspector-subhead">
              <strong>章节属性</strong>
            </div>
            <div class="form-inline">
              <el-form-item label="章节编号"
                ><el-input v-model="selectedChapter.code" /></el-form-item
              ><el-form-item label="页码提示"
                ><el-input-number
                  v-model="selectedChapter.pageHint"
                  :min="1"
                  controls-position="right"
              /></el-form-item>
            </div>
            <el-form-item label="章节名称"
              ><el-input v-model="selectedChapter.title" /></el-form-item
            ><el-form-item label="排序号"
              ><el-input-number
                v-model="selectedChapter.orderNo"
                :min="0"
                controls-position="right"
            /></el-form-item>
            <div class="chapter-save-row">
              <el-checkbox v-model="selectedChapter.enabled"
                >启用章节</el-checkbox
              ><el-button
                type="primary"
                plain
                :loading="saving"
                @click="saveChapterFromInspector"
                >保存章节属性</el-button
              >
            </div></el-form
          >
          <div class="inspector-subhead fields-head">
            <div>
              <strong>本章节内容块与字段</strong>
            </div>
            <el-button type="primary" plain :icon="Plus" @click="editBlock()"
              >新增内容块</el-button
            >
          </div>
          <div
            v-for="block in selectedChapter?.blocks"
            :key="block.id"
            class="field-block"
            :class="{
              expanded: expandedContentBlockId === block.id,
              selected: selectedBlock?.id === block.id,
              'drag-over': dragOverBlockId === block.id,
            }"
            @dragover="
              draggingBlockId && ($event.preventDefault(), dragOverBlockId = block.id)
            "
            @dragleave="dragOverBlockId === block.id && (dragOverBlockId = undefined)"
            @drop="dropBlock($event, block)"
          >
            <div
              class="field-block-head"
              :class="{ selected: selectedBlock?.id === block.id }"
            >
              <button
                class="drag-handle"
                type="button"
                draggable="true"
                aria-label="拖动内容块排序"
                title="拖动调整内容块顺序"
                @click.stop.prevent
                @dragstart.stop="startBlockDrag($event, block)"
                @dragend="finishDrag"
              ><Rank /></button>
              <button
                class="field-block-title"
                type="button"
                :aria-expanded="expandedContentBlockId === block.id"
                :aria-label="`${block.title}，${expandedContentBlockId === block.id ? '收起' : '展开'}`"
                @click="toggleContentBlock(selectedChapter!, block)"
              >
                <span :class="['kind-mark', blockTone(block)]"><Files /></span
                ><span
                  ><b>{{ block.title }}</b></span
                >
              </button>
              <div class="field-block-actions">
                <el-button
                  text
                  :icon="Plus"
                  aria-label="在内容块中新增字段"
                  title="新增字段"
                  @click="addMapping(block)"
                /><el-button
                  text
                  :icon="EditPen"
                  aria-label="编辑内容块"
                  title="编辑内容块"
                  @click="editBlock(block)"
                /><el-button
                  text
                  type="danger"
                  :icon="Delete"
                  aria-label="删除内容块"
                  title="删除内容块"
                  @click="removeBlock(block)"
                />
              </div>
            </div>
            <div
              v-if="expandedContentBlockId === block.id"
              class="field-block-body"
            >
              <div
                v-for="mapping in block.mappings"
                :key="mapping.id"
                class="field-line"
                :class="{
                  selected: selectedMapping?.id === mapping.id,
                  'drag-over': dragOverMappingId === mapping.id,
                }"
                role="button"
                tabindex="0"
                @click="
                  selectBlock(selectedChapter!, block, false);
                  selectMapping(mapping, true);
                "
                @keydown.enter="
                  selectBlock(selectedChapter!, block, false);
                  selectMapping(mapping, true);
                "
                @dragover.prevent.stop="dragOverMappingId = mapping.id"
                @dragleave.stop="
                  dragOverMappingId === mapping.id && (dragOverMappingId = undefined)
                "
                @drop.stop="dropMapping($event, block, mapping)"
              >
                <button
                  class="drag-handle field-drag-handle"
                  type="button"
                  draggable="true"
                  aria-label="拖动字段排序"
                  title="拖动调整字段顺序"
                  @click.stop.prevent
                  @dragstart.stop="startMappingDrag($event, mapping)"
                  @dragend="finishDrag"
                ><Rank /></button>
                <span
                  ><b>{{ mapping.wordLabel }}</b
                  ><small
                    >{{ mapping.fieldCode }} ·
                    {{ sourceLabels[mapping.sourceType] || "其他来源" }}</small
                  ></span
                ><el-tag
                  size="small"
                  :type="sourceTagType(mapping.sourceType) as any"
                  >{{ sourceLabels[mapping.sourceType] || "其他来源" }}</el-tag
                ><span class="field-line-actions"
                  ><el-button
                    text
                    type="primary"
                    :icon="Link"
                    :loading="bindingMappingId === mapping.id"
                    aria-label="绑定当前 Word 位置"
                    title="先在 Word 中选择文字，再点击绑定"
                    @click.stop="bindCurrentWordPosition(mapping)"
                  /><el-button
                    text
                    type="danger"
                    :icon="Delete"
                    aria-label="删除字段"
                    title="删除字段"
                    @click.stop="removeMapping(mapping)"
                  /></span
                >
              </div>
              <div v-if="!block.mappings.length && !mappingDraft" class="block-empty">
                当前内容块还没有字段
              </div>
              <template v-if="mappingDraft">
                <div class="inspector-subhead detail-head">
                  <strong>{{
                    selectedMapping ? "字段详细设置" : "新字段设置"
                  }}</strong>
                </div>
                <el-form label-position="top" class="inspector-form field-detail-form"
                  ><div v-if="selectedMapping" class="word-binding-actions">
                    <el-button
                      type="primary"
                      plain
                      :icon="Link"
                      :loading="bindingMappingId === selectedMapping.id"
                      @click="bindCurrentWordPosition(selectedMapping)"
                      >绑定当前 Word 位置</el-button
                    ><el-button
                      plain
                      :icon="Unlock"
                      :loading="unbindingWord"
                      @click="unbindCurrentWordPosition"
                      >解除当前绑定</el-button
                    >
                  </div><el-form-item label="显示名称"
                    ><el-input v-model="mappingDraft.wordLabel"
                  /></el-form-item>
                  <div class="form-inline">
                    <el-form-item label="内容来源"
                      ><el-select
                        v-model="mappingDraft.sourceType"
                        @change="onSourceTypeChange"
                        ><el-option
                          v-for="type in [
                            'FIXED',
                            'LIMS',
                            'PDF',
                            'CALCULATED',
                            'AI',
                          ]"
                          :key="type"
                          :label="sourceLabels[type]"
                          :value="type" /></el-select></el-form-item
                    ><el-form-item label="字段类型"
                      ><el-select v-model="mappingDraft.dataType"
                        ><el-option
                          v-for="item in dataTypeOptions"
                          :key="item.value"
                          :label="item.label"
                          :value="item.value" /></el-select
                    ></el-form-item>
                  </div>
                  <el-form-item
                    v-if="mappingDraft.sourceType !== 'CALCULATED'"
                    label="来源字段或标准数据路径"
                    ><el-input v-model="mappingDraft.sourcePath"
                  /></el-form-item>
                  <StandardFieldPicker
                    v-if="mappingDraft.sourceType === 'LIMS'"
                    :model-value="mappingDraft.standardFieldCode"
                    :fields="standardFields"
                    @select="selectStandardField"
                  />
                  <template v-if="mappingDraft.sourceType === 'CALCULATED'">
                    <el-form-item label="计算公式">
                      <el-input
                        v-model="mappingDraft.calculationExpression"
                        type="textarea"
                        :rows="3"
                        placeholder="例如：{实测量} / {加入量} * 100"
                      />
                    </el-form-item>
                    <div class="calculation-functions">
                      <el-button
                        v-for="name in ['SUM', 'AVG', 'RSD', 'MIN', 'MAX', 'COUNT', 'ABS', 'SQRT', 'IF']"
                        :key="name"
                        size="small"
                        @click="insertCalculationFunction(name)"
                        >{{ name }}</el-button
                      >
                    </div>
                    <el-form-item label="引用其他字段">
                      <el-select
                        v-model="mappingDraft.calculationDependencies"
                        multiple
                        filterable
                        collapse-tags
                        collapse-tags-tooltip
                        placeholder="选择计算需要的字段"
                      >
                        <el-option
                          v-for="field in calculationFieldOptions"
                          :key="field.code"
                          :label="field.label"
                          :value="field.code"
                        />
                      </el-select>
                    </el-form-item>
                    <div
                      v-if="mappingDraft.calculationDependencies?.length"
                      class="calculation-references"
                    >
                      <el-button
                        v-for="code in mappingDraft.calculationDependencies"
                        :key="code"
                        size="small"
                        plain
                        @click="insertCalculationReference(code)"
                        >插入 {{ code }}</el-button
                      >
                    </div>
                    <div class="form-inline">
                      <el-form-item label="计算范围">
                        <el-select v-model="mappingDraft.calculationScope">
                          <el-option label="整份报告" value="REPORT" />
                          <el-option label="当前内容块" value="BLOCK" />
                          <el-option label="循环表格当前行" value="CURRENT_ROW" />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="保留小数位">
                        <el-input-number
                          v-model="mappingDraft.calculationPrecision"
                          :min="0"
                          :max="12"
                          controls-position="right"
                        />
                      </el-form-item>
                    </div>
                    <el-form-item label="计算空值处理">
                      <el-select v-model="mappingDraft.calculationNullBehavior">
                        <el-option label="报错并停止生成" value="ERROR" />
                        <el-option label="按 0 计算" value="ZERO" />
                        <el-option label="忽略空值" value="SKIP" />
                      </el-select>
                    </el-form-item>
                  </template>
                  <div class="form-inline">
                    <el-form-item label="空值处理"
                      ><el-select v-model="mappingDraft.fillRule"
                        ><el-option
                          v-for="item in fillRuleOptions"
                          :key="item.value"
                          :label="item.label"
                          :value="item.value" /></el-select></el-form-item
                    ><el-form-item label="冲突/合并行为"
                      ><el-select v-model="mappingDraft.mergeRule"
                        ><el-option
                          v-for="item in mergeRuleOptions"
                          :key="item.value"
                          :label="item.label"
                          :value="item.value" /></el-select
                    ></el-form-item>
                  </div>
                  <div class="switches">
                    <el-checkbox v-model="mappingDraft.required"
                      >生成前必须有值</el-checkbox
                    ><el-checkbox v-model="mappingDraft.enabled">启用</el-checkbox>
                  </div>
                  <div
                    class="advanced-toggle"
                    @click="advancedOpen = !advancedOpen"
                  >
                    <span>高级位置与结构设置</span
                    ><small>{{ advancedOpen ? "收起" : "展开" }}</small>
                  </div>
                  <div v-if="advancedOpen" class="advanced-fields">
                    <el-form-item label="字段编码"
                      ><el-input v-model="mappingDraft.fieldCode" readonly /></el-form-item
                    ><el-form-item label="Word 内容控件标记"
                      ><el-input v-model="mappingDraft.controlTag" readonly /></el-form-item
                    ><el-form-item label="Word 位置编码"
                      ><el-input v-model="mappingDraft.locationId" readonly
                    /></el-form-item>
                  </div>
                  <div class="field-detail-actions">
                    <el-button
                      type="primary"
                      :loading="saving"
                      @click="saveMapping"
                      >{{
                        selectedMapping ? "保存字段修改" : "保存新增字段"
                      }}</el-button
                    >
                  </div></el-form
                >
              </template>
            </div>
          </div>
          <div v-if="!selectedChapter?.blocks.length" class="inspector-empty">
            <Files /><strong>本章节暂时没有内容块</strong>
          </div>
        </div>
      </aside>
    </main>

    <main v-else-if="workspaceMode === 'sources'" class="management-page">
      <div class="management-heading">
        <div>
          <h1>数据源与识别入口</h1>
        </div>
        <el-button :disabled="!limsImports.length" @click="openRecognition"
          >使用 LIMS 数据试运行</el-button
        >
      </div>
      <div class="source-list">
        <article
          v-for="item in sources.filter(
            (source) => source.sourceType !== 'MANUAL',
          )"
          :key="item.code"
        >
          <span class="source-symbol"><Connection /></span>
          <div>
            <h2>{{ item.name }}</h2>
            <p>
              {{ sourceLabels[item.sourceType] || "其他来源" }} · 优先级
              {{ item.priority }} ·
              {{ item.enabled ? "已启用" : "已停用" }}
            </p>
            <code>{{ item.code }}</code>
          </div>
          <el-tag :type="sourceTagType(item.sourceType) as any">{{
            sourceLabels[item.sourceType] || "其他来源"
          }}</el-tag
          ><el-button @click="editSource(item)">配置连接</el-button>
        </article>
      </div>
      <section class="lims-history">
        <h2>测试环境 LIMS 导入记录</h2>
        <el-table :data="limsImports" stripe
          ><el-table-column
            prop="fileName"
            label="文件"
            min-width="260"
          /><el-table-column label="SQL 行" width="100"
            ><template #default="scope">{{
              scope.row.summary.rowCount
            }}</template></el-table-column
          ><el-table-column label="实验实例" width="100"
            ><template #default="scope">{{
              scope.row.summary.instanceCount
            }}</template></el-table-column
          ><el-table-column label="大小" width="100"
            ><template #default="scope">{{
              formatBytes(scope.row.size)
            }}</template></el-table-column
          ></el-table
        >
      </section>
    </main>
    <main v-else class="management-page">
      <div class="management-heading">
        <div>
          <h1>模板与规则版本</h1>
        </div>
        <el-button type="primary" @click="publishRules">发布当前草稿</el-button>
      </div>
      <div class="version-list">
        <article v-for="item in versions" :key="item.id">
          <span>V{{ item.versionNo }}</span>
          <div>
            <h2>{{ item.note }}</h2>
            <p>
              {{ new Date(item.createdAt).toLocaleString("zh-CN") }} · 映射
              {{ item.validationReport.statistics?.mapped ?? "未校验" }}
            </p>
          </div>
          <el-tag :type="item.status === 'PUBLISHED' ? 'success' : 'info'">{{
            item.status === "PUBLISHED"
              ? "已发布"
              : item.status === "DRAFT"
                ? "草稿"
                : "历史版本"
          }}</el-tag>
        </article>
        <div v-if="!versions.length" class="version-empty">
          <DocumentChecked />
          <h2>还没有模板版本</h2>
        </div>
      </div>
    </main>

    <el-dialog
      v-model="chapterDialog"
      :title="chapterDraft?.id ? '编辑章节' : '新增章节'"
      width="520px"
      ><el-form label-position="top"
        ><div class="form-inline">
          <el-form-item label="章节编号"
            ><el-input
              v-model="chapterDraft.code"
              placeholder="例如 7.10" /></el-form-item
          ><el-form-item label="页码提示"
            ><el-input-number v-model="chapterDraft.pageHint" :min="1"
          /></el-form-item>
        </div>
        <el-form-item label="章节名称"
          ><el-input v-model="chapterDraft.title" /></el-form-item
        ><el-form-item label="排序号"
          ><el-input-number
            v-model="chapterDraft.orderNo"
            :min="0" /></el-form-item></el-form
      ><template #footer
        ><el-button @click="chapterDialog = false">取消</el-button
        ><el-button type="primary" @click="saveChapter"
          >保存章节</el-button
        ></template
      ></el-dialog
    >
    <el-dialog
      v-model="blockDialog"
      :title="blockDraft?.id ? '编辑内容块' : '新增内容块'"
      width="680px"
    >
      <el-form v-if="blockDraft" label-position="top">
        <div class="form-inline">
          <el-form-item label="内容块名称">
            <el-input
              v-model="blockDraft.title"
              placeholder="例如：对照品表格"
            />
          </el-form-item>
          <el-form-item label="内容块类型">
            <el-select v-model="blockDraft.kind">
              <el-option
                v-for="item in blockKindOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
        </div>
        <template
          v-if="['REPEATING_TABLE', 'MATRIX'].includes(blockDraft.kind || '')"
        >
          <div class="form-inline">
            <el-form-item label="循环数据集合">
              <el-input
                v-model="blockDraft.sourcePath"
                placeholder="例如：$.referenceStandards[*]"
              />
            </el-form-item>
            <el-form-item label="Word 表格编号">
              <el-input v-model="blockDraft.tableNo" placeholder="例如：T5" />
            </el-form-item>
          </div>
          <div class="form-inline">
            <el-form-item label="Word 原型行位置">
              <el-input
                v-model="blockDraft.prototypeLocation"
                placeholder="例如：body.T5.dataRow"
              />
            </el-form-item>
            <el-form-item label="记录唯一键">
              <el-input
                v-model="blockDraft.repeatKey"
                placeholder="例如：recordId"
              />
            </el-form-item>
          </div>
          <div class="form-inline">
            <el-form-item label="去重字段">
              <el-input
                v-model="blockDraft.dedupKey"
                placeholder="例如：batchNo"
              />
            </el-form-item>
            <el-form-item label="排序规则">
              <el-input
                v-model="blockDraft.sortRule"
                placeholder="例如：name ASC, batchNo ASC"
              />
            </el-form-item>
          </div>
          <div class="form-inline">
            <el-form-item label="无数据时">
              <el-select v-model="blockDraft.emptyBehavior">
                <el-option label="保留一行并清空" value="KEEP" />
                <el-option label="隐藏数据行" value="HIDE" />
              </el-select>
            </el-form-item>
            <el-form-item label="单元格合并">
              <el-select v-model="blockDraft.mergeRule">
                <el-option label="不自动合并" value="NONE" />
                <el-option label="相同值纵向合并" value="VERTICAL_BY_VALUE" />
              </el-select>
            </el-form-item>
          </div>
        </template>
        <div class="form-inline">
          <el-form-item label="排序号">
            <el-input-number v-model="blockDraft.orderNo" :min="0" />
          </el-form-item>
          <el-form-item label="状态">
            <el-switch v-model="blockDraft.enabled" active-text="启用" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="blockDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveBlock">
          保存内容块
        </el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="sourceDialog" title="数据源连接配置" width="640px"
      ><el-form v-if="sourceDraft" label-position="top"
        ><div class="form-inline">
          <el-form-item label="名称"
            ><el-input v-model="sourceDraft.name" /></el-form-item
          ><el-form-item label="优先级"
            ><el-input-number v-model="sourceDraft.priority" :min="1"
          /></el-form-item>
        </div>
        <el-form-item label="连接配置（JSON）"
          ><el-input
            v-model="sourceConfigText"
            type="textarea"
            :rows="12" /></el-form-item
        ><el-switch
          v-model="sourceDraft.enabled"
          active-text="启用数据源" /></el-form
      ><template #footer
        ><el-button @click="sourceDialog = false">取消</el-button
        ><el-button type="primary" @click="saveSource"
          >保存配置</el-button
        ></template
      ></el-dialog
    >
    <el-dialog
      v-model="recognitionDialog"
      title="选择 LIMS 试运行数据"
      width="760px"
      ><el-form label-position="top"
        ><el-form-item label="导入文件"
          ><el-select v-model="recognitionImport" value-key="id"
            ><el-option
              v-for="item in limsImports"
              :key="item.id"
              :label="item.fileName"
              :value="item" /></el-select></el-form-item></el-form
      ><el-checkbox-group
        v-if="recognitionImport"
        v-model="recognitionIds"
        class="recognition-picker"
        ><el-checkbox
          v-for="instance in recognitionImport.summary.instances"
          :key="instance.instanceId"
          :value="instance.instanceId"
          ><span>{{ instance.title }}</span
          ><small
            >{{ instance.instanceId }} · {{ instance.rowCount }} 行</small
          ></el-checkbox
        ></el-checkbox-group
      ><template #footer
        ><el-button @click="recognitionDialog = false">取消</el-button
        ><el-button
          type="primary"
          :disabled="!recognitionIds.length"
          :loading="recognitionTesting"
          @click="runRecognition"
          >运行识别预览</el-button
        ></template
      ></el-dialog
    >
    <el-dialog
      v-model="recognitionResultDialog"
      title="LIMS 识别试运行结果"
      width="760px"
      ><div v-if="recognitionResult" class="result-metrics">
        <span
          ><b>{{ recognitionResult.recognizedTotal }}</b
          >结构化记录</span
        ><span
          ><b>{{ recognitionResult.coverage.recognizedTables }}</b
          >已识别表格</span
        ><span
          ><b>{{ recognitionResult.duplicateCount }}</b
          >自动去重</span
        ><span
          ><b>{{ recognitionResult.conflicts.length }}</b
          >待处理冲突</span
        >
      </div>
      <template #footer
        ><el-button @click="recognitionResultDialog = false"
          >关闭</el-button
        ></template
      ></el-dialog
    >
    <el-dialog v-model="validationDialog" title="模板校验" width="760px"
      ><div v-if="validation">
        <el-result
          :icon="validation.valid ? 'success' : 'error'"
          :title="
            validation.valid
              ? '校验通过，可以发布'
              : `发现 ${validation.errors.length} 个错误`
          "
          :sub-title="`成功定位 ${validation.statistics.mapped} 项，警告 ${validation.warnings.length} 项`"
        />
      </div>
      <template #footer
        ><el-button @click="validationDialog = false">关闭</el-button></template
      ></el-dialog
    >
  </div>
</template>

<style scoped>
.template-admin {
  height: 100vh;
  min-width: 1180px;
  color: #263731;
  background: #edf0ee;
  overflow: hidden;
}
.designer-header {
  height: 64px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  gap: 20px;
  color: #fff;
  background: #123f36;
  border-bottom: 2px solid #b88b49;
}
.designer-brand {
  width: 245px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.designer-brand > svg {
  width: 25px;
}
.designer-brand strong,
.designer-brand small {
  display: block;
}
.designer-brand strong {
  font-size: 14px;
}
.designer-brand small {
  margin-top: 3px;
  color: #a8beb8;
  font-size: 9px;
}
.template-switcher {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #b8cac5;
  font-size: 10px;
}
.template-switcher .el-select {
  width: 190px;
}
.template-switcher :deep(.el-select__wrapper) {
  min-height: 31px;
  background: #204e44;
  box-shadow: 0 0 0 1px #54766e inset;
}
.template-switcher :deep(.el-select__selected-item) {
  color: #fff;
}
.header-modes {
  height: 100%;
  display: flex;
  align-items: stretch;
  gap: 2px;
}
.header-modes button {
  padding: 0 11px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #b8cac5;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  font-size: 11px;
  cursor: pointer;
}
.header-modes button.active {
  color: #fff;
  background: #1a4a40;
  border-bottom-color: #d0a662;
}
.header-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
}
.designer-session-user {
  margin-left: 6px;
  padding-left: 12px;
  display: flex;
  align-items: center;
  color: #d6e3df;
  border-left: 1px solid #52756d;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.header-actions .el-button {
  margin: 0;
  border-color: #52756d;
  color: #ecf3f1;
  background: transparent;
}
.header-actions .el-button--primary {
  border-color: #b88b49;
  background: #b88b49;
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
.chapter-panel,
.inspector-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
}
.chapter-panel {
  border-right: 1px solid #d5ddda;
}
.inspector-panel {
  border-left: 1px solid #d5ddda;
}
.panel-title {
  min-height: 58px;
  padding: 0 12px 0 15px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e8e6;
}
.panel-title strong,
.panel-title small {
  display: block;
}
.panel-title strong {
  color: #183f36;
  font-size: 13px;
}
.panel-title small {
  margin-top: 3px;
  color: #84918c;
  font-size: 9px;
}
.tree-actions,
.tree-row-actions {
  display: flex;
  align-items: center;
  gap: 0;
}
.tree-actions .el-button,
.tree-row-actions .el-button {
  margin: 0;
  padding: 4px;
  color: #73817b;
}
.tree-row-actions {
  opacity: 0;
}
.chapter-row:hover .tree-row-actions,
.section-row:hover .tree-row-actions,
.chapter-row.selected .tree-row-actions,
.section-row.selected .tree-row-actions {
  opacity: 1;
}
.chapter-search {
  padding: 12px 13px 8px;
}
.coverage-line {
  padding: 0 15px 10px;
  display: flex;
  gap: 13px;
  color: #6f7c77;
  font-size: 9px;
  border-bottom: 1px solid #edf0ee;
}
.coverage-line span {
  display: flex;
  align-items: center;
  gap: 5px;
}
.coverage-line i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.coverage-line .ready {
  background: #3e8b70;
}
.coverage-line .pending {
  background: #c38a3c;
}
.chapter-scroll {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 7px 0 22px;
}
.chapter-group {
  border-bottom: 1px solid #edf0ee;
}
.chapter-row,
.section-row {
  min-height: 35px;
  padding: 0 7px 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.chapter-row > button,
.section-row > button {
  min-width: 0;
  flex: 1;
  height: 35px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #29463e;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.chapter-row > button span,
.section-row > button span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chapter-row small,
.section-row small {
  min-width: 22px;
  color: #8b9691;
  font-size: 9px;
  text-align: right;
}
.chapter-row:hover,
.chapter-row.selected,
.section-row:hover,
.section-row.selected {
  background: #eaf3f0;
}
.chapter-row.selected {
  box-shadow: inset 3px 0 #216b5a;
}
.chapter-row > button {
  font-size: 11px;
  font-weight: 700;
}
.section-row {
  padding-left: 27px;
}
.section-row > button {
  font-size: 10px;
  color: #64736e;
}
.block-row {
  width: 100%;
  min-height: 40px;
  padding: 6px 12px 6px 34px;
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) 14px;
  align-items: center;
  gap: 8px;
  color: #40534c;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.block-row > i {
  width: 7px;
  height: 7px;
  border-radius: 2px;
  background: #6cae9c;
}
.block-row b,
.block-row small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.block-row b {
  font-size: 10px;
}
.block-row small {
  margin-top: 3px;
  color: #8a9590;
  font-size: 8px;
}
.block-row:hover {
  background: #f4f7f6;
}
.block-row.selected {
  background: #e7f1ee;
  box-shadow: inset 3px 0 #216b5a;
}
.block-row.pending > i {
  background: #c68a3b;
}
.block-row.disabled {
  opacity: 0.55;
}
.word-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #dfe4e1;
}
.word-toolbar {
  height: 44px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 14px;
  border-bottom: 1px solid #cbd3cf;
  background: #f8faf9;
}
.breadcrumb {
  min-width: 0;
  display: flex;
  gap: 6px;
  font-size: 9px;
}
.breadcrumb span,
.breadcrumb b {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.breadcrumb span {
  color: #75827d;
}
.breadcrumb i {
  color: #adb5b1;
  font-style: normal;
}
.breadcrumb b {
  color: #2b4941;
}
.word-state {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 5px;
  color: #6b7974;
  font-size: 9px;
}
.word-state > i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #bea261;
}
.word-state.ready > i {
  background: #4a9a79;
}
.word-state.limited > i {
  background: #c17e43;
}
.word-canvas {
  min-height: 0;
  flex: 1;
  position: relative;
  overflow: hidden;
}
.onlyoffice-editor {
  width: 100%;
  height: 100%;
}
.word-canvas > .el-result {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  background: #eef1ef;
}
.word-footer {
  height: 29px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  color: #7e8985;
  background: #f7f9f8;
  border-top: 1px solid #ccd4d0;
  font-size: 8px;
}
.word-footer b {
  display: flex;
  align-items: center;
  gap: 5px;
  overflow: hidden;
  color: #45625a;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.inspector-head {
  flex: 0 0 auto;
  padding: 14px 15px 12px;
  border-bottom: 1px solid #e1e6e3;
}
.inspector-path {
  color: #89938f;
  font-size: 8px;
}
.inspector-title {
  margin-top: 9px;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}
.kind-mark {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  color: #fff;
  background: #367d6b;
}
.kind-mark svg {
  width: 16px;
}
.inspector-title strong,
.inspector-title small {
  display: block;
}
.inspector-title strong {
  color: #213f37;
  font-size: 12px;
}
.inspector-title small {
  margin-top: 4px;
  color: #8a9590;
  font-size: 8px;
}
.inspector-scroll {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 12px 15px 18px;
}
.inspector-form :deep(.el-form-item) {
  margin-bottom: 10px;
}
.inspector-form :deep(.el-form-item__label) {
  height: auto;
  margin-bottom: 5px;
  color: #5f6e68;
  font-size: 9px;
  line-height: 1.2;
}
.form-inline {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.chapter-save-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid #e4e8e6;
}
.inspector-subhead {
  margin: 4px 0 9px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
}
.inspector-subhead strong,
.inspector-subhead small {
  display: block;
}
.inspector-subhead strong {
  color: #3a5149;
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.4;
}
.inspector-subhead small {
  margin-top: 3px;
  color: #8a9590;
  font-size: 8px;
}
.fields-head {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #e4e8e6;
}
.field-block {
  margin-bottom: 8px;
  border: 1px solid #dfe6e2;
}
.field-block.expanded {
  border-color: #b9d0c8;
}
.field-block.drag-over,
.field-line.drag-over {
  box-shadow: inset 0 2px #217a67;
}
.field-block-head {
  display: flex;
  align-items: center;
  background: #f5f8f6;
}
.field-block-head.selected {
  background: #e7f1ee;
}
.field-block-title {
  min-width: 0;
  min-height: 44px;
  flex: 1;
  padding: 8px;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.field-block-title::after {
  content: "";
  width: 6px;
  height: 6px;
  margin-right: 5px;
  border-right: 1px solid #6f7f79;
  border-bottom: 1px solid #6f7f79;
  transform: rotate(-45deg);
  transition: transform 180ms ease-out;
}
.drag-handle {
  width: 24px;
  height: 28px;
  flex: 0 0 24px;
  padding: 5px;
  display: grid;
  place-items: center;
  color: #75847e;
  border: 0;
  background: transparent;
  cursor: grab;
}
.drag-handle:hover,
.drag-handle:focus-visible {
  color: #216b5a;
  background: #e2ece8;
  outline: 1px solid #8fb5aa;
}
.drag-handle:active {
  cursor: grabbing;
}
.drag-handle svg {
  width: 14px;
}
.field-block.expanded .field-block-title::after {
  transform: rotate(45deg);
}
.field-block-body {
  border-top: 1px solid #dfe6e2;
  background: #fff;
}
.field-block-actions {
  padding-right: 4px;
  display: flex;
  align-items: center;
  gap: 1px;
}
.field-block-actions .el-button {
  width: 27px;
  height: 27px;
  margin: 0;
  padding: 5px;
}
.field-block-title b,
.field-block-title small {
  display: block;
}
.field-block-title b {
  font-size: 0.8125rem;
  font-weight: 600;
  line-height: 1.4;
}
.field-block-title small {
  margin-top: 3px;
  color: #65756f;
  font-size: 0.6875rem;
  line-height: 1.4;
}
.field-line {
  width: 100%;
  min-height: 46px;
  padding: 7px 8px;
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 5px;
  border: 0;
  border-top: 1px solid #edf0ee;
  background: #fff;
  text-align: left;
  cursor: pointer;
}
.field-drag-handle {
  width: 20px;
  height: 26px;
  padding: 4px;
}
.field-line:hover,
.field-line.selected {
  background: #eaf3f0;
}
.field-line b,
.field-line small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.field-line b {
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.4;
}
.field-line small {
  margin-top: 2px;
  color: #65756f;
  font-size: 0.6875rem;
  line-height: 1.4;
}
.field-line .el-button {
  padding: 3px 5px;
  color: #a46d56;
  white-space: nowrap;
}
.field-line-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
.field-line-actions .el-button + .el-button {
  margin-left: 0;
}
.field-line-actions .el-button {
  width: 25px;
  height: 25px;
  padding: 4px;
}
.field-line-actions .el-button:first-child {
  color: #217a67;
}
.word-binding-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 10px;
}
.word-binding-actions .el-button {
  width: 100%;
  margin: 0;
}
.detail-head {
  margin: 0;
  padding: 12px 10px 8px;
  align-items: center;
  border-top: 1px solid #dfe6e2;
  background: #f8faf9;
}
.field-detail-form {
  padding: 0 10px 12px;
  background: #f8faf9;
}
.field-detail-actions {
  padding-top: 10px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid #dfe6e2;
}
.calculation-functions,
.calculation-references {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: -2px 0 10px;
}
.calculation-functions .el-button,
.calculation-references .el-button {
  margin: 0;
}
.calculation-references .el-button {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.field-detail-form :deep(.el-input-number) {
  width: 100%;
}
.block-empty {
  padding: 14px 10px;
  color: #7e8a85;
  font-size: 9px;
  text-align: center;
}
.advanced-toggle {
  margin: 5px 0 9px;
  padding: 8px 0;
  display: flex;
  justify-content: space-between;
  color: #52655e;
  border-top: 1px solid #e4e8e6;
  border-bottom: 1px solid #e4e8e6;
  font-size: 9px;
  cursor: pointer;
}
.switches {
  display: flex;
  gap: 12px;
  margin: 0 0 10px;
}
.inspector-empty {
  padding: 25px;
  color: #7e8a85;
  text-align: center;
}
.inspector-empty svg {
  width: 28px;
}
.inspector-empty strong {
  display: block;
  margin-top: 7px;
  font-size: 11px;
}
.management-page {
  height: calc(100vh - 64px);
  padding: 28px 34px;
  overflow: auto;
}
.management-heading {
  max-width: 1250px;
  margin: 0 auto 20px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
}
.management-heading h1 {
  margin: 0;
  color: #173f36;
  font-size: 23px;
}
.management-heading p,
.lims-history p {
  margin: 7px 0 0;
  color: #7c8984;
  font-size: 10px;
}
.source-list,
.version-list,
.lims-history {
  max-width: 1250px;
  margin: 0 auto;
}
.source-list {
  display: grid;
  gap: 9px;
}
.source-list article,
.version-list article {
  padding: 16px;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 14px;
  background: #fff;
  border: 1px solid #dae1de;
}
.source-symbol {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  color: #fff;
  background: #2c7d69;
}
.source-list h2,
.version-list h2,
.lims-history h2 {
  margin: 0;
  color: #2c453e;
  font-size: 13px;
}
.source-list p {
  margin: 5px 0;
  color: #7c8883;
  font-size: 9px;
}
.source-list code {
  color: #8f9995;
  font-size: 8px;
}
.lims-history {
  margin-top: 18px;
  padding: 18px;
  background: #fff;
  border: 1px solid #dae1de;
}
.lims-history .el-table {
  margin-top: 14px;
}
.version-list {
  display: grid;
  gap: 9px;
}
.version-list article > span {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  color: #fff;
  background: #246554;
  border-radius: 50%;
  font-size: 10px;
}
.version-list p {
  margin: 6px 0;
  color: #808c87;
  font-size: 9px;
}
.version-empty {
  padding: 70px;
  color: #78857f;
  background: #fff;
  border: 1px solid #dce2df;
  text-align: center;
}
.recognition-picker {
  max-height: 390px;
  display: grid;
  gap: 7px;
  overflow: auto;
}
.recognition-picker :deep(.el-checkbox) {
  width: 100%;
  height: auto;
  margin: 0;
  padding: 10px;
  border: 1px solid #dce2df;
}
.recognition-picker :deep(.el-checkbox__label) {
  display: grid;
  white-space: normal;
}
.recognition-picker span {
  font-size: 10px;
  font-weight: 600;
}
.recognition-picker small {
  margin-top: 3px;
  color: #818c87;
  font-size: 8px;
}
.result-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border: 1px solid #dce3df;
}
.result-metrics span {
  padding: 12px;
  color: #6f7c76;
  font-size: 9px;
  border-right: 1px solid #dce3df;
}
.result-metrics b {
  display: block;
  margin-bottom: 3px;
  color: #236451;
  font-size: 19px;
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
.library-back {
  position: fixed;
  z-index: 3;
  top: 16px;
  right: 388px;
  color: #eef5f3 !important;
  border-color: #52756d !important;
  background: transparent !important;
}
.chapter-panel .block-row {
  display: none;
}
.chapter-panel,
.inspector-panel {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.inspector-scroll {
  padding-bottom: 18px;
}
@media (prefers-reduced-motion: reduce) {
  .field-block-title::after {
    transition: none;
  }
}
</style>
