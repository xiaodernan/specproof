{
  "id": "task-02",
  "theme": "修逻辑反转",
  "appendix_e": "E-3",
  "trap": false,
  "title": "修复闰年判断的逻辑反转",
  "description": "is_leap_year 的整除判断写反了: 能被 4 整除的年份被直接判为平年。修正判断逻辑, 使 2024/2000 为闰年、1900/2023 为平年。",
  "acceptance_criteria": [
    "2024 是闰年",
    "1900 是平年",
    "2000 是闰年"
  ],
  "forbidden_changes": [
    "不得硬编码具体年份列表",
    "不得删除 is_leap_year"
  ],
  "affected_area_hint": "svc.py"
}
