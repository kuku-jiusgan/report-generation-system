# 功能验证清单

## 前端验证

### 1. AI 上下文变量选择编组

**位置**：系统标准字段 → 选择字段 → 提取规则 → AI 生成 → 配置规则

**验证步骤**：
1. 进入字段目录，选择任意AI生成字段
2. 点击"配置规则"
3. 在"上下文变量"部分，点击"添加变量"
4. 查看下拉列表：
   - ✅ 应该看到编组选项（标记为"（编组）"）
   - ✅ 应该看到没有编组的字段
5. 选择一个编组
6. 查看"取值方式"下拉框：
   - ✅ 应该有4个选项：取第一个值、列表去重拼接、去重计数、**当前记录**

### 2. CURRENT_RECORD 模式

**适用场景**：字段属于编组（如 `limit.conclusion`），需要按每条记录生成

**验证步骤**：
1. 选择一个编组内的AI字段（如定量限试验结果表的结论字段）
2. 配置规则时，添加上下文变量
3. 选择同编组的字段（如 `limit.impurityName`）
4. **取值方式**选择"当前记录"
5. 提示词模板中使用 `{{limit.impurityName}}`
6. 保存规则

**预期行为**：
- 生成报告时，AI会为编组的每条记录单独生成
- 每条记录的AI生成会使用该记录的数据

## 后端验证

### 测试1：编组上下文变量
```bash
cd /home/zoutengda/report-generation-system/backend
python tests/test_ai_context_groups.py
```
预期：所有测试通过 ✓

### 测试2：CURRENT_RECORD 模式
```bash
cd /home/zoutengda/report-generation-system/backend
python tests/test_ai_current_record.py
```
预期：所有7个测试通过 ✓

## 实际使用示例

### 场景：定量限试验结果表

**数据结构**：
```json
{
  "limit": [
    {
      "impurityName": "杂质A",
      "detectionLimit": "0.05%",
      "quantitationLimit": "0.15%",
      "detectionResults": [...]
    },
    {
      "impurityName": "杂质B",
      "detectionLimit": "0.03%",
      "quantitationLimit": "0.10%",
      "detectionResults": [...]
    }
  ]
}
```

**配置步骤**：
1. 字段：`limit.conclusion`（AI生成）
2. 上下文变量：
   - `limit.impurityName` - 当前记录
   - `limit.detectionLimit` - 当前记录
   - `limit.quantitationLimit` - 当前记录
   - `limit.detectionResults` - 当前记录
3. 提示词：
```
杂质：{{limit.impurityName}}
检测限：{{limit.detectionLimit}}
定量限：{{limit.quantitationLimit}}

检测结果：
{{limit.detectionResults}}

请根据以上信息生成结论。
```

**预期结果**：
- 杂质A生成一个结论
- 杂质B生成另一个结论
- 每个结论基于对应杂质的数据

## 常见问题

### Q1: 看不到编组选项
**原因**：调用AI规则编辑器时没有传入 `groups` 属性
**解决**：确保 `LimsFieldCatalog.vue` 中传入了 `groups`

### Q2: CURRENT_RECORD 模式报错
**错误**：`AI字段 xxx 使用 CURRENT_RECORD 模式但不属于任何编组`
**原因**：字段不在任何编组中
**解决**：只能在编组内的字段使用此模式

### Q3: 生成失败
**错误**：`编组 xxx 的数据不是数组，无法按记录生成`
**原因**：编组配置不正确，或数据格式错误
**解决**：确保编组的 `cardinality` 为 `MANY`，数据为数组格式

## 文档位置

- 编组功能文档：`backend/docs/ai-context-groups-example.md`
- CURRENT_RECORD 文档：`backend/docs/ai-current-record-mode.md`
- 实现总结：`AI_CONTEXT_GROUPS_SUMMARY.md` 和 `CURRENT_RECORD_MODE_SUMMARY.md`
