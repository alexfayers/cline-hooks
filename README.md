# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/alexfayers/cline-hooks/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                    |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|-------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/cline\_hooks/\_\_init\_\_.py                        |        2 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/\_main.py                              |      152 |       24 |       42 |       10 |     81% |78, 134-136, 148, 164-165, 191, 197, 215, 225-231, 234-237, 245, 249-253 |
| src/cline\_hooks/config.py                              |        7 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/\_\_init\_\_.py                   |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/frontend.py                       |       46 |        3 |        8 |        1 |     89% |   133-135 |
| src/cline\_hooks/core/frontends.py                      |       21 |        2 |        4 |        1 |     88% |     42-43 |
| src/cline\_hooks/core/hook\_kwargs.py                   |       43 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/install.py                        |       96 |        1 |       32 |        1 |     98% |       192 |
| src/cline\_hooks/core/models.py                         |      130 |        5 |        8 |        1 |     96% |86-88, 188-189 |
| src/cline\_hooks/core/outcome.py                        |       40 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/core/parameters.py                     |       89 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/core/payload.py                        |      131 |        2 |       36 |        2 |     98% |  167, 311 |
| src/cline\_hooks/core/plugin.py                         |      203 |        6 |       58 |        3 |     97% |130-\>132, 187, 189, 361-364 |
| src/cline\_hooks/core/protocol.py                       |       84 |        4 |        8 |        1 |     95% |44-45, 220-221 |
| src/cline\_hooks/core/registry.py                       |       15 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/core/response.py                       |       34 |        0 |       12 |        0 |    100% |           |
| src/cline\_hooks/core/state.py                          |       46 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/core/timing.py                         |        5 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/transcript.py                     |       19 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/user\_install.py                  |       21 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/core/vocabulary.py                     |       53 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/\_\_init\_\_.py              |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/\_\_init\_\_.py  |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/install.py       |       19 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/models.py        |       29 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/protocol.py      |       68 |        1 |       16 |        0 |     99% |       151 |
| src/cline\_hooks/frontends/antigravity/transcript.py    |       34 |        0 |        8 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/\_\_init\_\_.py |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/install.py      |        8 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/models.py       |       48 |        0 |        8 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/protocol.py     |       68 |        1 |       16 |        2 |     96% |143, 155-\>157 |
| src/cline\_hooks/frontends/claude\_code/transcript.py   |      137 |        7 |       58 |        7 |     93% |145, 148, 182, 241, 247, 293, 296 |
| src/cline\_hooks/frontends/codex/\_\_init\_\_.py        |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/codex/install.py             |        8 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/codex/protocol.py            |       16 |        2 |        0 |        0 |     88% |    45, 49 |
| src/cline\_hooks/frontends/kiro/\_\_init\_\_.py         |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/kiro/install.py              |       17 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/frontends/kiro/models.py               |       16 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/kiro/protocol.py             |       36 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/frontends/pi/\_\_init\_\_.py           |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/pi/install.py                |       25 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/frontends/pi/models.py                 |       62 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/frontends/pi/protocol.py               |       38 |        1 |        4 |        1 |     95% |       115 |
| src/cline\_hooks/frontends/pi/transcript.py             |       51 |        4 |       16 |        2 |     91% |78-79, 87, 96 |
| src/cline\_hooks/handlers/\_\_init\_\_.py               |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/handlers/commands.py                   |      200 |        6 |       92 |        9 |     95% |238, 253, 280, 324, 328, 372, 381-\>377, 383-\>377, 384-\>383 |
| src/cline\_hooks/handlers/context\_nudge.py             |        7 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/handlers/git\_context.py               |       44 |        2 |        8 |        0 |     96% |     55-56 |
| src/cline\_hooks/handlers/herdr\_guard.py               |       79 |        1 |       24 |        1 |     98% |        84 |
| src/cline\_hooks/handlers/post\_tool\_use.py            |       44 |        2 |       12 |        2 |     93% |   54, 120 |
| src/cline\_hooks/handlers/pre\_compact.py               |       14 |        1 |        2 |        1 |     88% |        22 |
| src/cline\_hooks/handlers/pre\_tool\_use.py             |       66 |        4 |       18 |        3 |     92% |164, 179, 184-185 |
| src/cline\_hooks/handlers/push\_guard.py                |       22 |        0 |       10 |        0 |    100% |           |
| src/cline\_hooks/handlers/search\_scope.py              |      168 |        3 |       74 |        1 |     98% |248, 264-265 |
| src/cline\_hooks/handlers/stop.py                       |       41 |        0 |       12 |        0 |    100% |           |
| src/cline\_hooks/handlers/task\_lifecycle.py            |       78 |        1 |       12 |        1 |     98% |       161 |
| src/cline\_hooks/handlers/user\_prompt.py               |       28 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/plugins/\_\_init\_\_.py                |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/plugins/build\_tools.py                |       24 |        1 |        4 |        0 |     96% |        24 |
| src/cline\_hooks/plugins/checkout\_lock.py              |      134 |        5 |       42 |        4 |     95% |69-70, 125, 126-\>121, 128, 157 |
| src/cline\_hooks/plugins/command\_rules.py              |      111 |        5 |       42 |        3 |     95% |30-\>24, 158, 160-162, 214 |
| src/cline\_hooks/plugins/context\_usage.py              |       93 |        1 |       38 |        1 |     98% |       202 |
| src/cline\_hooks/plugins/delegation.py                  |       93 |        1 |       42 |        1 |     99% |       198 |
| src/cline\_hooks/plugins/ecosystem.py                   |       52 |        1 |       14 |        1 |     97% |44, 137-\>139 |
| src/cline\_hooks/plugins/fixup\_guard.py                |       58 |        0 |       14 |        0 |    100% |           |
| src/cline\_hooks/plugins/handback\_rescue.py            |       22 |        0 |        8 |        0 |    100% |           |
| src/cline\_hooks/plugins/handoff\_ack.py                |      143 |        0 |       56 |        1 |     99% | 275-\>277 |
| src/cline\_hooks/plugins/managed\_files.py              |       52 |        4 |       14 |        0 |     94% |20, 32, 47-48 |
| src/cline\_hooks/plugins/nudges.py                      |      171 |       12 |       70 |        5 |     91% |218-224, 241, 249, 332-\>334, 357, 362-\>368, 388, 408 |
| src/cline\_hooks/plugins/persistence.py                 |       26 |        1 |       10 |        1 |     94% |        50 |
| src/cline\_hooks/plugins/plan\_handoff.py               |       67 |        1 |       28 |        2 |     97% |144, 153-\>155 |
| src/cline\_hooks/plugins/research.py                    |      110 |        6 |       34 |        3 |     94% |129, 158-160, 219, 269-\>271, 276 |
| src/cline\_hooks/plugins/session\_context.py            |       19 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/plugins/shell\_guards.py               |       38 |        0 |       10 |        0 |    100% |           |
| src/cline\_hooks/plugins/skill\_guard.py                |       75 |        0 |       16 |        0 |    100% |           |
| src/cline\_hooks/plugins/startup\_blocks.py             |       81 |        1 |       20 |        0 |     99% |       145 |
| src/cline\_hooks/plugins/tool\_guards.py                |       90 |        3 |       36 |        1 |     97% |121-122, 157 |
| src/cline\_hooks/plugins/tool\_usage.py                 |       70 |        1 |       16 |        0 |     99% |        42 |
| src/cline\_hooks/plugins/tracking.py                    |       33 |        1 |       20 |        3 |     92% |32-\>exit, 60-\>62, 63 |
| src/cline\_hooks/state/\_\_init\_\_.py                  |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/agents.py                        |       32 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/state/finished.py                      |       24 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/jsonfile.py                      |       32 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/state/memory.py                        |       21 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/paths.py                         |        8 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/retrospective.py                 |       29 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/state/skills.py                        |       95 |        0 |       26 |        0 |    100% |           |
| src/cline\_hooks/state/store.py                         |       26 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/state/tool\_usage.py                   |       19 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/workspace.py                     |       24 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/uninstall.py                           |       34 |        2 |       10 |        1 |     93% |     51-52 |
| tests/\_\_init\_\_.py                                   |        0 |        0 |        0 |        0 |    100% |           |
| tests/conftest.py                                       |      169 |        2 |       14 |        0 |     99% |   56, 185 |
| tests/test\_agents\_tracker.py                          |       71 |        0 |        4 |        0 |    100% |           |
| tests/test\_bookkeeping\_tools.py                       |       11 |        0 |        0 |        0 |    100% |           |
| tests/test\_config.py                                   |       26 |        0 |        0 |        0 |    100% |           |
| tests/test\_context.py                                  |       77 |        0 |        0 |        0 |    100% |           |
| tests/test\_core\_frontend.py                           |      130 |        4 |        6 |        0 |     97% |27, 30, 33, 36 |
| tests/test\_core\_outcome.py                            |       88 |        0 |        0 |        0 |    100% |           |
| tests/test\_core\_parameters.py                         |       73 |        0 |        0 |        0 |    100% |           |
| tests/test\_core\_payload.py                            |      162 |        5 |       16 |        3 |     96% |48, 51, 54, 254-\>253, 256-257, 278-\>276 |
| tests/test\_core\_state.py                              |      121 |        0 |        4 |        0 |    100% |           |
| tests/test\_delegation\_tracker.py                      |       22 |        0 |        0 |        0 |    100% |           |
| tests/test\_finished\_tracker.py                        |       15 |        0 |        0 |        0 |    100% |           |
| tests/test\_frontend\_antigravity.py                    |       96 |        0 |        0 |        0 |    100% |           |
| tests/test\_frontend\_claude\_code\_transcript.py       |      143 |        0 |        0 |        0 |    100% |           |
| tests/test\_frontend\_conformance.py                    |      100 |        1 |       14 |        1 |     98% |        88 |
| tests/test\_frontend\_normalisation.py                  |      309 |        0 |        4 |        0 |    100% |           |
| tests/test\_frontend\_pi\_transcript.py                 |       39 |        0 |        4 |        0 |    100% |           |
| tests/test\_handlers\_commands.py                       |       77 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_context\_nudge.py                 |       95 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_git\_context.py                   |       42 |        0 |        2 |        0 |    100% |           |
| tests/test\_handlers\_post\_tool\_use.py                |      595 |        7 |       22 |        5 |     98% |511, 519, 731-732, 765-766, 922 |
| tests/test\_handlers\_pre\_compact.py                   |       19 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_pre\_tool\_use.py                 |      526 |        0 |       14 |        0 |    100% |           |
| tests/test\_handlers\_push\_guard.py                    |       28 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_search\_scope.py                  |      166 |        0 |        2 |        0 |    100% |           |
| tests/test\_handlers\_stop.py                           |      343 |        0 |        4 |        0 |    100% |           |
| tests/test\_handlers\_task\_lifecycle.py                |      341 |        7 |       10 |        4 |     97% |92-97, 141, 263-\>exit, 281-\>exit, 299-\>exit |
| tests/test\_handlers\_user\_prompt.py                   |      419 |        6 |       20 |        7 |     97% |138, 368-\>exit, 459-460, 593-\>exit, 609-\>exit, 659-\>exit, 703, 730, 748, 766-\>exit, 785-\>exit |
| tests/test\_hook\_kwargs.py                             |       64 |        0 |        0 |        0 |    100% |           |
| tests/test\_install.py                                  |      217 |        0 |       10 |        0 |    100% |           |
| tests/test\_install\_pi.py                              |       73 |        0 |        2 |        0 |    100% |           |
| tests/test\_kiro\_integration.py                        |       49 |        0 |        0 |        0 |    100% |           |
| tests/test\_main.py                                     |      123 |        2 |        4 |        0 |     98% |  205, 211 |
| tests/test\_memory\_tracker.py                          |       66 |        0 |        4 |        0 |    100% |           |
| tests/test\_models.py                                   |      108 |        0 |        4 |        0 |    100% |           |
| tests/test\_models\_kiro.py                             |      213 |        0 |        2 |        0 |    100% |           |
| tests/test\_pi\_extension.py                            |       90 |        0 |        6 |        0 |    100% |           |
| tests/test\_plan.py                                     |       45 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugin.py                                   |      168 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugin\_entry\_points.py                    |       80 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugin\_extension\_points.py                |       27 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_build\_tools.py                    |       17 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_checkout\_lock.py                  |       97 |        0 |        6 |        0 |    100% |           |
| tests/test\_plugins\_command\_rules.py                  |       55 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_delegation.py                      |       76 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_ecosystem.py                       |      112 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_fixup\_guard.py                    |       62 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_handback\_rescue.py                |       27 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_handoff\_ack.py                    |      304 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_nested\_calls.py                   |       49 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_research.py                        |       41 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_shell\_guards.py                   |       63 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_skill\_guard.py                    |      130 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_startup\_blocks.py                 |      142 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_tool\_usage.py                     |       68 |        0 |        8 |        0 |    100% |           |
| tests/test\_readme\_matrix.py                           |       41 |        0 |        6 |        0 |    100% |           |
| tests/test\_registry.py                                 |       49 |        5 |        0 |        0 |     90% |24, 30, 40, 44, 68 |
| tests/test\_research\_tracker.py                        |       50 |        0 |        0 |        0 |    100% |           |
| tests/test\_response.py                                 |      200 |        0 |        0 |        0 |    100% |           |
| tests/test\_retrospective\_tracker.py                   |       78 |        0 |       10 |        0 |    100% |           |
| tests/test\_skill\_tracker.py                           |       86 |        0 |        8 |        0 |    100% |           |
| tests/test\_state.py                                    |       67 |        0 |        4 |        0 |    100% |           |
| tests/test\_state\_jsonfile.py                          |       65 |        0 |        6 |        0 |    100% |           |
| tests/test\_state\_paths.py                             |        8 |        0 |        0 |        0 |    100% |           |
| tests/test\_state\_tool\_usage.py                       |       20 |        0 |        4 |        0 |    100% |           |
| tests/test\_turns.py                                    |       57 |        1 |        6 |        0 |     98% |        22 |
| tests/test\_uninstall.py                                |       46 |        0 |        0 |        0 |    100% |           |
| tests/test\_user\_install.py                            |       53 |        0 |        4 |        0 |    100% |           |
| tests/test\_workspace.py                                |       80 |        0 |        4 |        0 |    100% |           |
| **TOTAL**                                               | **12401** |  **169** | **1492** |   **97** | **98%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/alexfayers/cline-hooks/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/alexfayers/cline-hooks/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/alexfayers/cline-hooks/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/alexfayers/cline-hooks/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Falexfayers%2Fcline-hooks%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/alexfayers/cline-hooks/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.