# AI 上下文变量支持编组 - 修改总结

## 需求
在标准字段目录的AI生成规则配置中，上下文变量原本只能选择字段，现在需要改成可以选择编组。对于没有编组的字段，仍然显示字段。

## 修改内容

### 1. 前端修改

#### `SystemContextVariables.vue` - 上下文变量选择器
- **类型定义**：`ContextVariable` 类型现在支持 `fieldCode?` 和 `groupCode?`（二选一）
- **选项构建**：
  - 优先显示所有编组（标记为"（编组）"）
  - 显示没有编组的字段
- **双向绑定**：根据选择的是编组还是字段，自动设置对应的 code

#### `SystemAiRuleEditor.vue` - AI规则编辑器
- 添加 `groups` 属性，接收编组列表
- 将编组数据传递给 `SystemContextVariables` 组件

#### `LimsFieldCatalog.vue` - 字段目录管理界面
- 在调用 AI 规则编辑器和计算规则配置时，传入 `groups` 数据
- 编组数据来自 `list_system_field_groups`

### 2. 后端修改

#### `admin_routes/rule_catalog.py` - 验证逻辑
- **验证AI规则**时：
  - 分别验证 `fieldCode` 和 `groupCode` 是否存在
  - 检查提示词中引用的变量是否都已配置
  - 要求每个变量必须有 `fieldCode` 或 `groupCode` 之一

#### `services/ai_field_generator.py` - AI生成核心
- **`context_variables()`**：接受包含 `groupCode` 的变量
- **`resolve_context_values()`**：
  - 对于 `fieldCode`：按原有方式处理（FIRST/JOIN_UNIQUE/COUNT_UNIQUE）
  - 对于 `groupCode`：将整个编组数据序列化为 JSON 字符串传给 AI
  - 编组数据缺失时使用默认值或标记为缺失

#### `services/system_field_resolver.py` - 字段解析
- **`resolve_system_fields()`**：
  - `values` 字典不仅包含字段值，还包含编组数据
  - 从字段的 `collectionCode` 中识别编组
  - 从 `legacyJsonPath` 推导编组的数据路径并读取

#### `main.py` - 依赖收集
- 修改依赖收集逻辑，明确区分字段依赖和编组依赖
- 编组数据从 payload 直接读取，不需要加入字段依赖链

### 3. 数据流

```
用户选择 → 前端配置 → 后端验证 → 存储
                                    ↓
生成报告 → 读取配置 → 构建values字典（字段值+编组数据）→ AI生成
```

#### values 字典结构示例：
```python
{
  # 字段值
  "project.name": "项目X",
  "instrument.model": "仪器A",

  # 编组数据（JSON字符串）
  "samples": [
    {"sampleName": "样品A", "batchNo": "20240101"},
    {"sampleName": "样品B", "batchNo": "20240102"}
  ]
}
```

## 优势

1. **更丰富的上下文**：AI 可以访问完整的表格数据结构，而不仅仅是拼接后的文本
2. **保留数据关系**：AI 可以理解字段间的对应关系（如样品名对应批号）
3. **更智能的生成**：AI 可以根据数据结构做更复杂的分析和总结
4. **向后兼容**：原有的 `fieldCode` 配置继续有效

## 测试验证

所有核心功能已通过测试：
- ✅ 接受 `fieldCode` 的上下文变量
- ✅ 接受 `groupCode` 的上下文变量
- ✅ 混合使用字段和编组
- ✅ 字段值按原方式解析
- ✅ 编组数据序列化为 JSON
- ✅ 缺失数据的默认值处理
- ✅ 后端验证逻辑

## 使用示例

### 前端配置
在"系统标准字段"→ 选择字段 → "提取规则" → "AI 生成"中：
1. 点击"添加变量"
2. 在下拉列表中选择编组（如"样品信息（编组）"）或字段
3. 在提示词模板中使用 `{{samples}}` 引用编组数据
4. AI 将收到完整的 JSON 结构

### 提示词示例
```
以下是样品数据：
{{samples}}

请根据这些样品的名称、批号和浓度生成检测摘要。
```

AI 接收到的内容：
```
以下是样品数据：
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

请根据这些样品的名称、批号和浓度生成检测摘要。
```

## 文件清单

### 修改的文件
- `frontend/src/SystemContextVariables.vue` - 上下文变量选择器
- `frontend/src/SystemAiRuleEditor.vue` - AI规则编辑器
- `frontend/src/LimsFieldCatalog.vue` - 字段目录界面
- `backend/app/admin_routes/rule_catalog.py` - 后端验证
- `backend/app/services/ai_field_generator.py` - AI生成核心
- `backend/app/services/system_field_resolver.py` - 字段解析
- `backend/app/main.py` - 依赖收集

### 新增的文件
- `backend/tests/test_ai_context_groups.py` - 单元测试
- `backend/docs/ai-context-groups-example.md` - 使用文档
- `AI_CONTEXT_GROUPS_SUMMARY.md` - 本文档
