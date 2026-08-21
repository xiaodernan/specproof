{
  "id": "task-41",
  "category": "code",
  "theme": "真实工程: 构建脚本排除模式 (fnmatch)",
  "appendix_e": "V-41",
  "trap": false,
  "title": "collect_sources 支持 glob 排除模式",
  "description": "build.collect_sources 把 exclude 当精确文件名比对, 'test_*.py' 这类 glob 模式不生效, 测试文件被打进构建产物。契约: exclude 按 fnmatch 模式匹配; 返回排序后的 .py 文件列表; 非 .py 与隐藏文件跳过。",
  "acceptance_criteria": [
    "exclude 支持 glob 模式 (test_*.py)",
    "结果排序稳定",
    "非 .py 与隐藏文件不打包"
  ],
  "forbidden_changes": [
    "不得引入第三方依赖 (仅标准库)"
  ],
  "affected_area_hint": "build.py"
}
