{
  "id": "task-25",
  "category": "code",
  "theme": "多文件: 事件发布幂等",
  "appendix_e": "V-25",
  "trap": false,
  "title": "publish 对同一 key 只投递一次",
  "description": "api.publish 调 service.publish_event 时未做幂等, 同一 key 重复发布会在outbox 里产生重复记录。契约: 同一 key 只保留第一条 (幂等); 不同 key 各自保留; outbox 顺序稳定。",
  "acceptance_criteria": [
    "同一 key 重复发布只产生一条记录",
    "不同 key 各自保留",
    "发布顺序保持稳定"
  ],
  "forbidden_changes": [
    "不得改变 publish_event 的函数签名"
  ],
  "affected_area_hint": "api.py, service.py"
}
