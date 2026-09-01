# mbs-ig-media

Публичный relay медиа для MBS Dashboard.

## Постоянные обложки аналитики

Workflow `.github/workflows/mirror-instagram-covers.yml` получает обложки через
официальный Meta Graph API на GitHub runner, где нет ограничения RU-хостинга, и
публикует стабильные файлы вместе с `instagram-covers/manifest.json`.

- запуск возможен только по расписанию или вручную из GitHub Actions;
- workflow не имеет `pull_request`, `pull_request_target` или
  `repository_dispatch` trigger;
- `MBS_META_ACCESS_TOKEN` — GitHub Actions Secret, он не хранится в Git и не
  выводится в логи;
- manifest содержит только public `media_id`, content type и стабильный raw URL,
  без временных Meta URL и токенов.

Первый запуск выполняют в режиме `smoke`, затем после ручной проверки — в режиме
`full`. Обычное расписание зеркалит последние 40 media каждый час.
