{
  "id": "task-44",
  "category": "code",
  "theme": "真实工程: 版本号递增遗漏预发布段",
  "appendix_e": "V-44",
  "trap": false,
  "title": "next_version 支持带预发布段的版本号",
  "description": "version.next_version 的正则只认 x.y.z, '1.2.3-rc1' 直接 ValueError。契约: 接受可选 '-<prerelease>' 段; bump (major/minor/patch) 后丢弃预发布段并低位归零; 非法版本抛 ValueError。",
  "acceptance_criteria": [
    "next_version('1.2.3-rc1', 'patch') == '1.2.4'",
    "major/minor bump 低位归零",
    "非法版本抛 ValueError"
  ],
  "forbidden_changes": [
    "不得引入第三方依赖 (仅标准库 re)"
  ],
  "affected_area_hint": "version.py"
}
