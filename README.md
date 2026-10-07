# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/alexfayers/cline-hooks/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                    |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|-------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/cline\_hooks/\_\_init\_\_.py                        |        2 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/\_main.py                              |      120 |       22 |       32 |        5 |     78% |70, 106-108, 117-120, 136-137, 163, 184-193, 197-201 |
| src/cline\_hooks/config.py                              |        7 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/\_\_init\_\_.py                   |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/frontend.py                       |       31 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/core/frontends.py                      |       26 |        2 |        8 |        1 |     91% |     42-43 |
| src/cline\_hooks/core/hook\_kwargs.py                   |       43 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/install.py                        |       67 |        0 |       16 |        0 |    100% |           |
| src/cline\_hooks/core/models.py                         |      116 |        5 |        8 |        1 |     95% |86-88, 180-181 |
| src/cline\_hooks/core/outcome.py                        |       34 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/core/parameters.py                     |       70 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/core/payload.py                        |      122 |        2 |       34 |        2 |     97% |  163, 293 |
| src/cline\_hooks/core/plugin.py                         |      180 |        6 |       52 |        3 |     96% |86-\>88, 137, 139, 311-314 |
| src/cline\_hooks/core/protocol.py                       |       81 |        7 |        8 |        1 |     89% |44-45, 174-176, 198-199 |
| src/cline\_hooks/core/registry.py                       |       15 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/core/response.py                       |       26 |        1 |        8 |        1 |     94% |        64 |
| src/cline\_hooks/core/state.py                          |       38 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/core/timing.py                         |        5 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/transcript.py                     |       19 |        2 |        0 |        0 |     89% |    53, 80 |
| src/cline\_hooks/core/vocabulary.py                     |       45 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/\_\_init\_\_.py              |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/\_\_init\_\_.py  |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/install.py       |       18 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/models.py        |       29 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/protocol.py      |       67 |        1 |       16 |        0 |     99% |       149 |
| src/cline\_hooks/frontends/antigravity/transcript.py    |       34 |        0 |        8 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/\_\_init\_\_.py |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/install.py      |        8 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/models.py       |       45 |        0 |        8 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/protocol.py     |       57 |        1 |       12 |        2 |     96% |129, 141-\>143 |
| src/cline\_hooks/frontends/claude\_code/transcript.py   |      137 |        7 |       58 |        7 |     93% |145, 148, 182, 241, 247, 293, 296 |
| src/cline\_hooks/frontends/cline/\_\_init\_\_.py        |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/cline/install.py             |       76 |       10 |       22 |        4 |     86% |20, 33-34, 60, 63-67, 70-75, 77, 78-\>84 |
| src/cline\_hooks/frontends/cline/protocol.py            |       38 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/frontends/codex/\_\_init\_\_.py        |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/codex/install.py             |        8 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/codex/protocol.py            |       15 |        2 |        0 |        0 |     87% |    39, 43 |
| src/cline\_hooks/frontends/copilot/\_\_init\_\_.py      |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/copilot/install.py           |       12 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/copilot/models.py            |        6 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/copilot/protocol.py          |       25 |        3 |        2 |        1 |     85% |75, 80, 84 |
| src/cline\_hooks/frontends/kiro/\_\_init\_\_.py         |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/kiro/install.py              |       17 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/frontends/kiro/models.py               |       16 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/kiro/protocol.py             |       35 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/frontends/pi/\_\_init\_\_.py           |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/pi/install.py                |       25 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/frontends/pi/models.py                 |       45 |        1 |        4 |        1 |     96% |        96 |
| src/cline\_hooks/frontends/pi/protocol.py               |       27 |        3 |        2 |        1 |     86% |82, 87, 91 |
| src/cline\_hooks/handlers/\_\_init\_\_.py               |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/handlers/commands.py                   |      115 |        5 |       64 |       10 |     92% |53, 80, 84, 88, 95-\>94, 122, 129-\>127, 131-\>127, 133-\>127, 134-\>133 |
| src/cline\_hooks/handlers/context\_nudge.py             |        7 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/handlers/git\_context.py               |       33 |       14 |        4 |        1 |     59% |     23-46 |
| src/cline\_hooks/handlers/post\_tool\_use.py            |       43 |        2 |       12 |        2 |     93% |   53, 118 |
| src/cline\_hooks/handlers/pre\_compact.py               |       14 |        1 |        2 |        1 |     88% |        22 |
| src/cline\_hooks/handlers/pre\_tool\_use.py             |       67 |       10 |       18 |        4 |     84% |78, 82-84, 119-120, 159, 174, 179-180 |
| src/cline\_hooks/handlers/push\_guard.py                |       23 |        0 |       10 |        0 |    100% |           |
| src/cline\_hooks/handlers/search\_scope.py              |      163 |        3 |       72 |        1 |     98% |240, 256-257 |
| src/cline\_hooks/handlers/stop.py                       |       38 |        0 |       10 |        0 |    100% |           |
| src/cline\_hooks/handlers/task\_lifecycle.py            |       63 |        1 |       10 |        1 |     97% |       121 |
| src/cline\_hooks/handlers/user\_prompt.py               |       21 |        0 |        4 |        1 |     96% | 54-\>exit |
| src/cline\_hooks/plugins/\_\_init\_\_.py                |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/plugins/build\_tools.py                |       24 |        1 |        4 |        0 |     96% |        24 |
| src/cline\_hooks/plugins/command\_rules.py              |       37 |        5 |       10 |        3 |     79% |28-\>22, 31-35, 73 |
| src/cline\_hooks/plugins/context\_usage.py              |       89 |        1 |       34 |        1 |     98% |       199 |
| src/cline\_hooks/plugins/delegation.py                  |       74 |        2 |       28 |        2 |     96% |  154, 186 |
| src/cline\_hooks/plugins/ecosystem.py                   |       52 |        1 |       14 |        1 |     97% |44, 133-\>135 |
| src/cline\_hooks/plugins/handback\_rescue.py            |       22 |        0 |        8 |        0 |    100% |           |
| src/cline\_hooks/plugins/managed\_files.py              |       53 |        3 |       18 |        1 |     94% | 31, 48-49 |
| src/cline\_hooks/plugins/nudges.py                      |      156 |       18 |       62 |        5 |     87% |217-223, 235-247, 308-\>310, 333, 338-\>340, 360, 380 |
| src/cline\_hooks/plugins/persistence.py                 |       23 |        0 |        8 |        0 |    100% |           |
| src/cline\_hooks/plugins/plan\_handoff.py               |       67 |        1 |       28 |        2 |     97% |144, 153-\>155 |
| src/cline\_hooks/plugins/research.py                    |      103 |        6 |       32 |        3 |     93% |120, 147-149, 202, 252-\>254, 259 |
| src/cline\_hooks/plugins/session\_context.py            |       19 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/plugins/shell\_guards.py               |       50 |        2 |       14 |        0 |     97% |     40-41 |
| src/cline\_hooks/plugins/tool\_guards.py                |       80 |        3 |       34 |        1 |     96% |90-91, 123 |
| src/cline\_hooks/plugins/tracking.py                    |       36 |        1 |       22 |        3 |     93% |33-\>exit, 63-\>65, 66 |
| src/cline\_hooks/state/\_\_init\_\_.py                  |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/agents.py                        |       22 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/jsonfile.py                      |       32 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/state/memory.py                        |       21 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/paths.py                         |        7 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/retrospective.py                 |       29 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/state/skills.py                        |       45 |        0 |       10 |        0 |    100% |           |
| src/cline\_hooks/state/store.py                         |       26 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/state/workspace.py                     |       24 |        0 |        6 |        0 |    100% |           |
| tests/\_\_init\_\_.py                                   |        0 |        0 |        0 |        0 |    100% |           |
| tests/conftest.py                                       |      133 |        1 |       12 |        0 |     99% |       142 |
| tests/test\_agents\_tracker.py                          |       71 |        0 |        4 |        0 |    100% |           |
| tests/test\_config.py                                   |       26 |        0 |        0 |        0 |    100% |           |
| tests/test\_context.py                                  |       61 |        0 |        0 |        0 |    100% |           |
| tests/test\_core\_frontend.py                           |      108 |        4 |        6 |        0 |     96% |25, 28, 31, 34 |
| tests/test\_core\_outcome.py                            |       74 |        0 |        0 |        0 |    100% |           |
| tests/test\_core\_parameters.py                         |       64 |        0 |        0 |        0 |    100% |           |
| tests/test\_core\_payload.py                            |      162 |        5 |       16 |        2 |     96% |48, 51, 54, 254-\>253, 256-257 |
| tests/test\_core\_state.py                              |      111 |        0 |        4 |        0 |    100% |           |
| tests/test\_delegation\_tracker.py                      |       22 |        0 |        0 |        0 |    100% |           |
| tests/test\_frontend\_antigravity.py                    |       96 |        0 |        0 |        0 |    100% |           |
| tests/test\_frontend\_claude\_code\_transcript.py       |      143 |        0 |        0 |        0 |    100% |           |
| tests/test\_frontend\_conformance.py                    |      114 |        1 |       18 |        1 |     98% |       105 |
| tests/test\_frontend\_normalisation.py                  |      300 |        0 |        4 |        0 |    100% |           |
| tests/test\_handlers\_commands.py                       |       63 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_context\_nudge.py                 |       70 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_post\_tool\_use.py                |      459 |        9 |       24 |        6 |     97% |369, 377, 445-446, 452-453, 486-487, 641 |
| tests/test\_handlers\_pre\_compact.py                   |       19 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_pre\_tool\_use.py                 |      470 |        0 |       14 |        0 |    100% |           |
| tests/test\_handlers\_push\_guard.py                    |       28 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_search\_scope.py                  |      163 |        0 |        2 |        0 |    100% |           |
| tests/test\_handlers\_stop.py                           |      303 |        0 |        4 |        0 |    100% |           |
| tests/test\_handlers\_task\_lifecycle.py                |      305 |        7 |        8 |        4 |     96% |89-94, 138, 254-\>exit, 272-\>exit, 290-\>exit |
| tests/test\_handlers\_user\_prompt.py                   |      334 |        4 |       20 |        7 |     97% |136, 325-\>exit, 416-417, 508-\>exit, 524-\>exit, 553-\>exit, 577, 595-\>exit, 614-\>exit |
| tests/test\_hook\_kwargs.py                             |       64 |        0 |        0 |        0 |    100% |           |
| tests/test\_install.py                                  |      178 |        0 |       10 |        0 |    100% |           |
| tests/test\_install\_cline.py                           |       76 |        0 |        6 |        0 |    100% |           |
| tests/test\_install\_pi.py                              |       40 |        0 |        2 |        0 |    100% |           |
| tests/test\_kiro\_integration.py                        |       55 |        0 |        0 |        0 |    100% |           |
| tests/test\_main.py                                     |      113 |        2 |        2 |        0 |     98% |  179, 185 |
| tests/test\_memory\_tracker.py                          |       66 |        0 |        4 |        0 |    100% |           |
| tests/test\_models.py                                   |      108 |        0 |        4 |        0 |    100% |           |
| tests/test\_models\_kiro.py                             |      213 |        0 |        2 |        0 |    100% |           |
| tests/test\_plan.py                                     |       45 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugin.py                                   |      149 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugin\_entry\_points.py                    |       80 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugin\_extension\_points.py                |       27 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_build\_tools.py                    |       17 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_command\_rules.py                  |       25 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_delegation.py                      |       70 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_ecosystem.py                       |      112 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_handback\_rescue.py                |       27 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_research.py                        |       30 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_shell\_guards.py                   |       21 |        0 |        0 |        0 |    100% |           |
| tests/test\_readme\_matrix.py                           |       40 |        0 |        6 |        0 |    100% |           |
| tests/test\_registry.py                                 |       49 |        5 |        0 |        0 |     90% |24, 30, 40, 44, 68 |
| tests/test\_research\_tracker.py                        |       45 |        0 |        0 |        0 |    100% |           |
| tests/test\_response.py                                 |      199 |        0 |        0 |        0 |    100% |           |
| tests/test\_retrospective\_tracker.py                   |       78 |        0 |       10 |        0 |    100% |           |
| tests/test\_skill\_tracker.py                           |       86 |        0 |        8 |        0 |    100% |           |
| tests/test\_state.py                                    |       67 |        0 |        4 |        0 |    100% |           |
| tests/test\_state\_jsonfile.py                          |       65 |        0 |        6 |        0 |    100% |           |
| tests/test\_turns.py                                    |      104 |        1 |       12 |        1 |     98% |       164 |
| tests/test\_workspace.py                                |       80 |        0 |        4 |        0 |    100% |           |
| **TOTAL**                                               | **9517** |  **194** | **1114** |   **94** | **97%** |           |


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