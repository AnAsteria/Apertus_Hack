# Распределение Bern Match: Maxim, Ruihan, Dimitry

Предложение распределения от 18 октября 2026, 14:21 Europe/Zurich. До дедлайна 19 октября, 14:30 остаётся примерно 24 часа 9 минут на момент проверки. Это не подтверждение плана, не dispatcher grant и не запуск реализации. Актуальные статусы задач остаются в GitHub. Полные зависимости и критерии — в [плане](tasks/README.md) и соответствующих issues.

## Ответственность

| Участник | Основная область | Дополнительная ответственность |
| --- | --- | --- |
| Maxim — AI/ML | Источники, ingestion, evidence storage, индексы и hybrid search | T14 evaluation harness/gold set; координатор T22 материалов сдачи |
| Ruihan — AI/ML | Inference API, Apertus extraction, grounding, interpretation, assessment, измерения | Предлагаемый единственный владелец общих контрактов; помощь с локальным Apertus для T15 |
| Dimitry — CS/coding/prompting | Каркас, API/UI, CI, deployment, admin, интеграция | Предлагаемый единственный dispatcher/integration owner; финальная упаковка и submission |

Роли dispatcher и contract owner требуют явного назначения человеком. T01 требует согласования всех троих. Для балансировки предлагается передать ведущую ответственность за T14 и T22 Maxim: сейчас specifications/issues относят их к B и C соответственно. До подтверждения это предложение, а не изменение действующих границ файлов. После подтверждения dispatcher синхронизирует владельцев/границы в task specifications и issues; GitHub handles участников не предоставлены, поэтому account assignees не назначены.

При такой передаче оценочная нагрузка: Maxim 29 ч, Ruihan 28.5 ч, Dimitry 27 ч обязательной работы плюс 4 ч отложенного Stretch. Это оценки активной работы без ожиданий; обязательные 84.5 человеко-часа превышают примерно 72.4 грубых человеко-часа до дедлайна на момент проверки, ещё до сна и координации. Распределение не устраняет дефицит времени. Не обещать выполнение всего Core; недостающие требования явно фиксировать.

## Maxim: основной порядок

1. [T02 / #2](https://github.com/AnAsteria/Apertus_Hack/issues/2): подтвердить источники и небольшие реальные страницы всех трёх организаций, URL/ограничения/языки; подготовить ожидаемые сущности.
2. [T06 / #6](https://github.com/AnAsteria/Apertus_Hack/issues/6): после интеграции T02 и T04 — bounded crawl, версии документов, passages/sentence IDs, coverage. Передать Ruihan реальные данные для T07 и T08.
3. [T14 / #14](https://github.com/AnAsteria/Apertus_Hack/issues/14): после T01/T02/T04, пока Ruihan делает extraction/grounding — 30–50 source-grounded запросов, intent-level split, gold/equivalence rules и harness. Ожидаемые ответы определить до прогона системы. Передача ведущей ответственности требует подтверждения.
4. [T09 / #9](https://github.com/AnAsteria/Apertus_Hack/issues/9): после T06 и T08 — persisted BM25+dense, max entity aggregation, deduplication/MMR, multilingual retrieval. Подготовку интерфейса/fixtures можно делать ранее только в согласованном grant; реальная приёмка требует T08.
5. [T12 / #12](https://github.com/AnAsteria/Apertus_Hack/issues/12): после T09 — freshness, manual refresh, removal/suppression и retirement. Передать Dimitry интерфейсы lifecycle для T13.
6. [T15 / #15](https://github.com/AnAsteria/Apertus_Hack/issues/15): после T03/T05/T09 — unseen query без сети с локальными embeddings, indexes и настоящим Apertus 8B. Подготовку аппаратуры/загрузки начать раньше через согласованную область T03, помощь Ruihan; не ждать конца проекта для скачивания моделей.

T14 и T09 — приоритетные переключения по готовности: если T08 уже интегрирован, сначала разблокировать работающий поиск T09; harness не должен искусственно задержать первый deployment. Обе задачи должны быть завершены для своих зависимых проверок.

[T22 / #22](https://github.com/AnAsteria/Apertus_Hack/issues/22) идёт частями с раннего этапа после T01: Maxim ведёт pitch/story и общую структуру, Ruihan даёт AI/evaluation/cost разделы отчёта, Dimitry — видео приложения/deployment и финальные ссылки. Максимальная длина: pitch 10 слайдов, report 6 страниц, видео 2 минуты. Это материалы подачи, не Stretch brief. Финализация требует настоящих измерений T16/T20 и release evidence T25. Один ведущий не означает параллельное редактирование одного файла: согласовать секции/файлы через dispatcher.

## Ruihan: основной порядок

1. [T03 / #3](https://github.com/AnAsteria/Apertus_Hack/issues/3): проверить endpoint/models/доступ, structured output и streaming как ожидаемые возможности, доступный host и локальное железо. Секреты не писать в issue. Подтвердить аппаратные/модельные ограничения для T15.
2. [T05 / #5](https://github.com/AnAsteria/Apertus_Hack/issues/5): после T03/T04 — server-side конфигурация inference, реальные capability probes, timeout/retry/concurrency, инструментирование и replaceable local endpoint. Неподдерживаемое constrained decoding явно отделить от validation/retry fallback.
3. [T07 / #7](https://github.com/AnAsteria/Apertus_Hack/issues/7): после T05/T06 — 8B extraction по реальным страницам, schema validation и sentence-ID evidence.
4. [T08 / #8](https://github.com/AnAsteria/Apertus_Hack/issues/8): после T07 — entity resolution, контакты/роли, semantic grounding. Передать Maxim результат для T09. Приоритетно разблокировать эту зависимость.
5. [T16 / #16](https://github.com/AnAsteria/Apertus_Hack/issues/16): после T11/T12/T14 — actual Core benchmarks, latency/token/throughput measurements, cost worksheet. Пока эти входы не готовы, после T11 можно выполнять независимую T18, не объявляя T16 завершённой.
6. [T18 / #18](https://github.com/AnAsteria/Apertus_Hack/issues/18): после T05/T11 — editable needs и multilingual query expansion без блокировки first cards; согласовать UI изменения с Dimitry.
7. [T19 / #19](https://github.com/AnAsteria/Apertus_Hack/issues/19): после T08/T18 — bounded batched assessment и streamed validated enrichment, evidence/need coverage/categories.
8. [T20 / #20](https://github.com/AnAsteria/Apertus_Hack/issues/20): после T16/T19 — полный BM25/dense/hybrid/expansion/assessment ablation и open cross-encoder subset, реальные измерения и ошибки.

T16 Core имеет приоритет, как только его входы готовы. T18/T19 — Second layer, но их отсутствие оставляет обязательные T20 сравнения неполными; это нужно раскрыть, а не скрыть за сокращением scope. Результаты/конфигурации передать Maxim для отчёта и Dimitry для release gate. T15 помогать только в согласованных областях, не редактируя файлы Maxim без grant.

## Dimitry: основной порядок

1. [T01 / #1](https://github.com/AnAsteria/Apertus_Hack/issues/1): организовать совместное утверждение минимального stack/contracts, ownership, lifecycle policy и integration rules. Зафиксировать именованные роли после назначения человеком.
2. [T04 / #4](https://github.com/AnAsteria/Apertus_Hack/issues/4): после T01 — каркас приложения, contracts/fixtures, CI/container, health/readiness. Это разблокирует T05 и T06.
3. [T10 / #10](https://github.com/AnAsteria/Apertus_Hack/issues/10): после T04 — UI/API на явно синтетических fixtures, затем подключение T09. Fixture UI не означает working real-data search.
4. [T11 / #11](https://github.com/AnAsteria/Apertus_Hack/issues/11): после T03/T05/T09/T10 — объединить реальный pipeline и сделать ранний внешний deployment, persistent indexes, серверные secrets, restart/smoke test. Если host недоступен — явный blocker, не выдуманный public URL.
   **Открытое решение для Dimitry (T03 → T11):** хостинг ещё не выбран. Варианты из [access-readiness](access-readiness.md#4-hosting-options-for-the-dispatcher-no-purchase-or-provisioning-done): (1) Hugging Face Space (Docker) — быстрее всего и публичный URL, но не в Швейцарии, постоянное хранилище может быть платным; (2) швейцарская VM (Infomaniak / Exoscale) — лучше всего для аргумента о суверенитете, но платная и требует явного разрешения; (3) машина участника + туннель — бесплатно, но ненадёжно для доступа жюри. Образ T04 (`Dockerfile`, `/data`, `/healthz`) подходит для всех трёх. Решение нужно до чекпоинта 18:00; ничего не покупать и не создавать без явного разрешения.
5. [T13 / #13](https://github.com/AnAsteria/Apertus_Hack/issues/13): после T11/T12 — feedback persistence и защищённый admin/manual refresh.
6. [T17 / #17](https://github.com/AnAsteria/Apertus_Hack/issues/17): после T13/T15/T16 — проверить интегрированный Core; незакрытые требования оставляют gate открытым.
7. [T25 / #25](https://github.com/AnAsteria/Apertus_Hack/issues/25): после T17/T20/T21 — final deployment/repository/docs/secret checks и проверка публичного URL извне.
8. [T26 / #26](https://github.com/AnAsteria/Apertus_Hack/issues/26): после T22/T25 — PDF ZIP, видео/ссылки/длительность/страницы, checklist и actual submission confirmation.

[T21 / #21](https://github.com/AnAsteria/Apertus_Hack/issues/21) выполнять в первом доступном окне после T11/T14: partner review, фиксация feedback и адресные исправления через владельцев модулей. Организационную подготовку начать раньше; не отправлять сообщения без разрешения. Не откладывать review до T25. Во время T18/T19 Dimitry согласованно подключает enrichment UI; это часть задач Ruihan, не независимое изменение общих интерфейсов.

[T23 / #23](https://github.com/AnAsteria/Apertus_Hack/issues/23) и [T24 / #24](https://github.com/AnAsteria/Apertus_Hack/issues/24) по умолчанию отложены: brief только после принятого Core/T19 и защищённого времени сдачи, email после brief, никогда automatic sending. Пока обязательные release задачи не закрыты, не брать их вместо сдачи.

## Общие передачи и checkpoints

1. Сначала параллельно T02 Maxim, T03 Ruihan и совместное T01 под координацией Dimitry. Не начинать код до утверждения плана/контрактов и записанного grant.
2. После T04 параллельно: Maxim T06, Ruihan T05, Dimitry T10. Реальные sentence-ID данные передаются из T06 в T07/T08, затем entities из T08 в T09, затем search API в T10/T11.
3. После первого deployment: Maxim T12/T15, Ruihan T16 или T18 по готовности, Dimitry T13/partner review. Документы и видео готовятся частями, не в последние 30 минут.
4. До final release должны сойтись Core T17, полные сравнения T20, partner T21 и материалы T22. Не заменять evidence неподтверждёнными обещаниями.
5. Сохранить существующие агрессивные checkpoints как ориентиры: сегодня 18:00 first deployed slice; 19 октября 08:00 Core evidence, 10:30 freeze enrichment/evaluation, 12:30 final app/artifacts freeze, 13:30 package/accessibility checks. Последний час **13:30–14:30 Europe/Zurich** — submission buffer. Это цели, не подтверждённые сроки выполнения. Если срыв очевиден, записать решение о scope и ограничения заранее.

Один issue — один grant/branch/worktree; общие контракты меняются только через Ruihan после назначения, интеграция — через Dimitry после назначения. Не считать назначение GitHub аккаунта атомарной блокировкой. Статус DONE — только после проверки интегрированного результата.
