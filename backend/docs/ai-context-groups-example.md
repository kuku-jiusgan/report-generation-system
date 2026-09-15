# AI 生成字段的上下文变量支持编组

## 功能说明

在配置 AI 生成字段时，上下文变量现在支持两种类型：

1. **字段（fieldCode）**：单个字段的值，按取值方式处理（FIRST/JOIN_UNIQUE/COUNT_UNIQUE）
2. **编组（groupCode）**：整个编组的数据（对象或数组），序列化为 JSON 供 AI 使用

## 使用场景

### 场景 1：使用单个字段（原有功能）

```json
{
  "contextVariables": [
    {
      "fieldCode": "project.name",
      "mode": "FIRST",
      "required": true,
      "defaultValue": ""
    }
  ],
  "promptTemplate": "项目名称：{{project.name}}\n请生成项目摘要。"
}
```

### 场景 2：使用编组（新功能）

当 AI 需要访问整个样品列表的结构化数据时：

```json
{
  "contextVariables": [
    {
      "groupCode": "samples",
      "required": true,
      "defaultValue": ""
    }
  ],
  "promptTemplate": "以下是样品数据：\n{{samples}}\n\n请根据这些样品生成检测摘要。"
}
```

AI 将收到类似这样的 JSON 数据：

```json
[
  {
    "sampleName": "样品A",
    "batchNo": "20240101",
    "concentration": "1.4%"
  },
  {
    "sampleName": "样品B",
    "batchNo": "20240102",
    "concentration": "0.3%"
  }
]
```

### 场景 3：混合使用字段和编组

```json
{
  "contextVariables": [
    {
      "fieldCode": "project.name",
      "mode": "FIRST",
      "required": true,
      "defaultValue": ""
    },
    {
      "groupCode": "samples",
      "required": true,
      "defaultValue": ""
    },
    {
      "fieldCode": "instrument.model",
      "mode": "FIRST",
      "required": false,
      "defaultValue": "未指定"
    }
  ],
  "promptTemplate": "项目：{{project.name}}\n仪器：{{instrument.model}}\n\n样品数据：\n{{samples}}\n\n请生成实验报告摘要。"
}
```

## 前端配置界面

在"系统标准字段"的"提取规则"配置中，AI 生成规则的"上下文变量"选择器会显示：

- **编组**（标记为"（编组）"）：对于有字段的编组
- **单个字段**：对于没有编组的字段

选择编组后，AI 可以访问该编组的完整结构化数据。

## 数据传递机制

1. **字段值**：从 payload 按字段的 `legacyJsonPath` 读取，经过取值方式处理后传给 AI
2. **编组数据**：从 payload 按编组的 `collectionCode` 读取完整数组或对象，序列化为 JSON 后传给 AI

## 优势

- **更丰富的上下文**：AI 可以看到完整的表格数据，而不仅仅是拼接后的文本
- **保留数据结构**：AI 可以理解字段之间的关系（如样品名称对应批号）
- **更灵活的生成**：AI 可以根据数据结构做出更智能的决策

## 向后兼容

- 原有的 `fieldCode` 配置继续有效
- 旧的 `inputFields` 数组格式仍被支持（自动转换为 `contextVariables`）
