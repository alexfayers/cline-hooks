# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/alexfayers/cline-hooks/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                    |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|-------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| conftest.py                                             |       11 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/\_\_init\_\_.py                        |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/\_main.py                              |      251 |       23 |       60 |        9 |     89% |179, 243-245, 262, 303-304, 364, 380-386, 389-392, 400-401, 405-409 |
| src/cline\_hooks/config.py                              |       11 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/\_\_init\_\_.py                   |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/frontend.py                       |       51 |        3 |       10 |        1 |     90% |   147-149 |
| src/cline\_hooks/core/frontends.py                      |       21 |        2 |        4 |        1 |     88% |     42-43 |
| src/cline\_hooks/core/hook\_kwargs.py                   |       45 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/install.py                        |      158 |        4 |       56 |        3 |     97% |239, 299-300, 309 |
| src/cline\_hooks/core/models.py                         |      132 |        5 |        8 |        1 |     96% |88-90, 190-191 |
| src/cline\_hooks/core/outcome.py                        |       37 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/core/parameters.py                     |       89 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/core/payload.py                        |      138 |        2 |       38 |        2 |     98% |  169, 329 |
| src/cline\_hooks/core/plugin.py                         |      214 |        6 |       62 |        3 |     97% |136-\>138, 199, 201, 373-376 |
| src/cline\_hooks/core/protocol.py                       |       87 |        2 |        8 |        1 |     97% |   231-232 |
| src/cline\_hooks/core/registry.py                       |       15 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/core/response.py                       |       34 |        0 |       12 |        0 |    100% |           |
| src/cline\_hooks/core/state.py                          |      141 |        2 |       36 |        2 |     98% |  162, 166 |
| src/cline\_hooks/core/timing.py                         |        5 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/transcript.py                     |       19 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/core/user\_install.py                  |       21 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/core/vocabulary.py                     |       54 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/\_\_init\_\_.py              |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/\_\_init\_\_.py  |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/install.py       |       19 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/models.py        |       29 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/antigravity/protocol.py      |       68 |        1 |       16 |        0 |     99% |       151 |
| src/cline\_hooks/frontends/antigravity/transcript.py    |       34 |        0 |        8 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/\_\_init\_\_.py |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/install.py      |        8 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/models.py       |       48 |        0 |        8 |        0 |    100% |           |
| src/cline\_hooks/frontends/claude\_code/protocol.py     |       70 |        2 |       16 |        2 |     95% |143, 155-\>157, 191 |
| src/cline\_hooks/frontends/claude\_code/transcript.py   |      137 |        7 |       58 |        7 |     93% |145, 148, 182, 241, 247, 293, 296 |
| src/cline\_hooks/frontends/codex/\_\_init\_\_.py        |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/codex/install.py             |        8 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/codex/protocol.py            |       16 |        2 |        0 |        0 |     88% |    45, 49 |
| src/cline\_hooks/frontends/kiro/\_\_init\_\_.py         |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/kiro/install.py              |       17 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/frontends/kiro/models.py               |       16 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/kiro/protocol.py             |       36 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/frontends/opencode/\_\_init\_\_.py     |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/opencode/install.py          |       19 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/frontends/opencode/models.py           |       75 |        0 |       24 |        2 |     98% |94-\>106, 106-\>108 |
| src/cline\_hooks/frontends/opencode/protocol.py         |       37 |        1 |        2 |        0 |     97% |       119 |
| src/cline\_hooks/frontends/pi/\_\_init\_\_.py           |        3 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/pi/install.py                |       16 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/frontends/pi/models.py                 |       63 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/frontends/pi/protocol.py               |       40 |        1 |        4 |        1 |     95% |       115 |
| src/cline\_hooks/frontends/pi/transcript.py             |       55 |        2 |       18 |        3 |     93% |72-\>67, 93, 102 |
| src/cline\_hooks/handlers/\_\_init\_\_.py               |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/handlers/commands.py                   |      212 |        6 |       96 |       10 |     95% |264, 279, 306, 350, 354, 400, 407-\>405, 409-\>405, 411-\>405, 412-\>411 |
| src/cline\_hooks/handlers/context\_nudge.py             |        7 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/handlers/git\_context.py               |       54 |        3 |       12 |        1 |     94% | 33-34, 89 |
| src/cline\_hooks/handlers/herdr\_guard.py               |       79 |        1 |       24 |        1 |     98% |        84 |
| src/cline\_hooks/handlers/post\_tool\_use.py            |       47 |        2 |       14 |        2 |     93% |   55, 124 |
| src/cline\_hooks/handlers/pre\_compact.py               |       14 |        1 |        2 |        1 |     88% |        22 |
| src/cline\_hooks/handlers/pre\_tool\_use.py             |       76 |        4 |       22 |        3 |     93% |192, 207, 212-213 |
| src/cline\_hooks/handlers/push\_guard.py                |       22 |        0 |       10 |        0 |    100% |           |
| src/cline\_hooks/handlers/search\_scope.py              |      276 |        6 |      104 |        2 |     98% |409, 425-426, 501-502, 582 |
| src/cline\_hooks/handlers/stop.py                       |       41 |        0 |       12 |        0 |    100% |           |
| src/cline\_hooks/handlers/task\_lifecycle.py            |       78 |        1 |       12 |        1 |     98% |       161 |
| src/cline\_hooks/handlers/user\_prompt.py               |       28 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/plugins/\_\_init\_\_.py                |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/plugins/agent\_worktree.py             |       35 |        2 |        8 |        0 |     95% |     23-24 |
| src/cline\_hooks/plugins/background\_watch.py           |       23 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/plugins/bash\_timeout.py               |       16 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/plugins/build\_redirect.py             |       54 |        3 |       10 |        0 |     95% |     94-96 |
| src/cline\_hooks/plugins/build\_tools.py                |       24 |        1 |        4 |        0 |     96% |        24 |
| src/cline\_hooks/plugins/checkout\_lock.py              |      134 |        5 |       42 |        4 |     95% |69-70, 125, 126-\>121, 128, 157 |
| src/cline\_hooks/plugins/command\_rules.py              |      224 |        7 |       90 |        5 |     96% |31-\>25, 159, 230, 293, 328-329, 352, 427 |
| src/cline\_hooks/plugins/context\_usage.py              |      100 |        1 |       40 |        1 |     99% |       211 |
| src/cline\_hooks/plugins/delegation.py                  |       93 |        1 |       42 |        1 |     99% |       204 |
| src/cline\_hooks/plugins/ecosystem.py                   |       52 |        1 |       14 |        1 |     97% |44, 137-\>139 |
| src/cline\_hooks/plugins/file\_structure.py             |       39 |        5 |       12 |        2 |     86% |58, 63, 67-69 |
| src/cline\_hooks/plugins/fixup\_guard.py                |       58 |        0 |       14 |        0 |    100% |           |
| src/cline\_hooks/plugins/fork\_guard.py                 |       41 |        2 |       14 |        2 |     93% |    42, 67 |
| src/cline\_hooks/plugins/handback\_rescue.py            |       22 |        0 |        8 |        0 |    100% |           |
| src/cline\_hooks/plugins/handoff\_ack.py                |      143 |        0 |       56 |        1 |     99% | 275-\>277 |
| src/cline\_hooks/plugins/managed\_files.py              |       52 |        4 |       14 |        0 |     94% |20, 32, 47-48 |
| src/cline\_hooks/plugins/nudges.py                      |      174 |       12 |       70 |        5 |     91% |218-224, 241, 249, 332-\>334, 357, 362-\>368, 388, 409 |
| src/cline\_hooks/plugins/persistence.py                 |       26 |        1 |       10 |        1 |     94% |        50 |
| src/cline\_hooks/plugins/plan\_handoff.py               |       69 |        1 |       28 |        2 |     97% |146, 155-\>157 |
| src/cline\_hooks/plugins/research.py                    |      110 |        6 |       34 |        3 |     94% |129, 158-160, 219, 269-\>271, 276 |
| src/cline\_hooks/plugins/session\_context.py            |       19 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/plugins/shell\_guards.py               |       43 |        0 |       12 |        0 |    100% |           |
| src/cline\_hooks/plugins/skill\_guard.py                |       94 |        1 |       26 |        1 |     98% |        91 |
| src/cline\_hooks/plugins/startup\_blocks.py             |       81 |        1 |       20 |        0 |     99% |       145 |
| src/cline\_hooks/plugins/tool\_guards.py                |       91 |        3 |       36 |        1 |     97% |123-124, 160 |
| src/cline\_hooks/plugins/tool\_usage.py                 |       70 |        1 |       16 |        0 |     99% |        42 |
| src/cline\_hooks/plugins/tracking.py                    |       35 |        1 |       22 |        2 |     95% |32-\>exit, 65 |
| src/cline\_hooks/state/\_\_init\_\_.py                  |        0 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/agents.py                        |       21 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/disabled\_plugins.py             |       26 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/state/finished.py                      |       24 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/jsonfile.py                      |       33 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/state/memory.py                        |       35 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/state/path\_migration.py               |       77 |       17 |       28 |        6 |     72% |53-63, 64-\>66, 67, 107, 109, 113-114, 150 |
| src/cline\_hooks/state/paths.py                         |       27 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/state/retrospective.py                 |       29 |        0 |        4 |        0 |    100% |           |
| src/cline\_hooks/state/skills.py                        |       88 |        0 |       26 |        0 |    100% |           |
| src/cline\_hooks/state/store.py                         |       26 |        0 |        2 |        0 |    100% |           |
| src/cline\_hooks/state/tool\_paths.py                   |       14 |        3 |        4 |        2 |     72% | 23-24, 34 |
| src/cline\_hooks/state/tool\_usage.py                   |       19 |        0 |        0 |        0 |    100% |           |
| src/cline\_hooks/state/workspace.py                     |       24 |        0 |        6 |        0 |    100% |           |
| src/cline\_hooks/uninstall.py                           |       34 |        2 |       10 |        1 |     93% |     51-52 |
| tests/\_\_init\_\_.py                                   |        0 |        0 |        0 |        0 |    100% |           |
| tests/conftest.py                                       |      175 |        2 |       14 |        0 |     99% |   58, 187 |
| tests/test\_agents\_tracker.py                          |       71 |        0 |        4 |        0 |    100% |           |
| tests/test\_bookkeeping\_tools.py                       |       11 |        0 |        0 |        0 |    100% |           |
| tests/test\_config.py                                   |       26 |        0 |        0 |        0 |    100% |           |
| tests/test\_context.py                                  |       83 |        0 |        0 |        0 |    100% |           |
| tests/test\_core\_frontend.py                           |      130 |        4 |        6 |        0 |     97% |27, 30, 33, 36 |
| tests/test\_core\_outcome.py                            |       88 |        0 |        0 |        0 |    100% |           |
| tests/test\_core\_parameters.py                         |       73 |        0 |        0 |        0 |    100% |           |
| tests/test\_core\_payload.py                            |      162 |        5 |       16 |        3 |     96% |48, 51, 54, 254-\>253, 256-257, 278-\>276 |
| tests/test\_core\_state.py                              |      235 |        0 |       14 |        0 |    100% |           |
| tests/test\_delegation\_tracker.py                      |       22 |        0 |        0 |        0 |    100% |           |
| tests/test\_finished\_tracker.py                        |       15 |        0 |        0 |        0 |    100% |           |
| tests/test\_frontend\_antigravity.py                    |       96 |        0 |        0 |        0 |    100% |           |
| tests/test\_frontend\_claude\_code\_transcript.py       |      143 |        0 |        0 |        0 |    100% |           |
| tests/test\_frontend\_conformance.py                    |      101 |        1 |       14 |        1 |     98% |        89 |
| tests/test\_frontend\_normalisation.py                  |      387 |        0 |        4 |        0 |    100% |           |
| tests/test\_frontend\_opencode.py                       |       62 |        0 |        2 |        0 |    100% |           |
| tests/test\_frontend\_pi\_transcript.py                 |       52 |        0 |        4 |        0 |    100% |           |
| tests/test\_handlers\_commands.py                       |       84 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_context\_nudge.py                 |      113 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_git\_context.py                   |       67 |        0 |        2 |        0 |    100% |           |
| tests/test\_handlers\_post\_tool\_use.py                |      623 |        7 |       22 |        5 |     98% |521, 529, 741-742, 805-806, 962 |
| tests/test\_handlers\_pre\_compact.py                   |       19 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_pre\_tool\_use.py                 |      582 |        0 |       18 |        0 |    100% |           |
| tests/test\_handlers\_push\_guard.py                    |       28 |        0 |        0 |        0 |    100% |           |
| tests/test\_handlers\_search\_scope.py                  |      200 |        0 |        2 |        0 |    100% |           |
| tests/test\_handlers\_stop.py                           |      351 |        0 |        6 |        0 |    100% |           |
| tests/test\_handlers\_task\_lifecycle.py                |      353 |        7 |       10 |        4 |     97% |96-101, 148, 278-\>exit, 296-\>exit, 314-\>exit |
| tests/test\_handlers\_user\_prompt.py                   |      438 |        6 |       22 |        7 |     97% |139, 371-\>exit, 462-463, 598-\>exit, 614-\>exit, 664-\>exit, 733, 760, 778, 796-\>exit, 815-\>exit |
| tests/test\_hook\_kwargs.py                             |       64 |        0 |        0 |        0 |    100% |           |
| tests/test\_install.py                                  |      240 |        0 |       10 |        0 |    100% |           |
| tests/test\_install\_bridge.py                          |       71 |        0 |        6 |        0 |    100% |           |
| tests/test\_install\_opencode.py                        |       20 |        0 |        0 |        0 |    100% |           |
| tests/test\_install\_pi.py                              |       39 |        0 |        2 |        0 |    100% |           |
| tests/test\_kiro\_integration.py                        |       49 |        0 |        0 |        0 |    100% |           |
| tests/test\_main.py                                     |      293 |        4 |       10 |        1 |     98% |184, 262, 397, 403 |
| tests/test\_memory\_tracker.py                          |       85 |        0 |        4 |        0 |    100% |           |
| tests/test\_models.py                                   |      108 |        0 |        4 |        0 |    100% |           |
| tests/test\_models\_kiro.py                             |      213 |        0 |        2 |        0 |    100% |           |
| tests/test\_opencode\_plugin.py                         |      152 |        0 |        8 |        0 |    100% |           |
| tests/test\_pi\_extension.py                            |      142 |        0 |       10 |        0 |    100% |           |
| tests/test\_plan.py                                     |       45 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugin.py                                   |      177 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugin\_entry\_points.py                    |       80 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugin\_extension\_points.py                |       27 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_agent\_worktree.py                 |       51 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_background\_watch.py               |       54 |        0 |        6 |        1 |     98% |   50-\>54 |
| tests/test\_plugins\_bash\_timeout.py                   |       22 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_build\_redirect.py                 |       95 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_build\_tools.py                    |       17 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_checkout\_lock.py                  |       99 |        0 |        6 |        0 |    100% |           |
| tests/test\_plugins\_command\_rules.py                  |       63 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_delegation.py                      |       85 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_ecosystem.py                       |      112 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_file\_structure.py                 |       46 |        0 |        6 |        0 |    100% |           |
| tests/test\_plugins\_fixup\_guard.py                    |       62 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_fork\_guard.py                     |       40 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_handback\_rescue.py                |       27 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_handoff\_ack.py                    |      304 |        0 |        0 |        0 |    100% |           |
| tests/test\_plugins\_nested\_calls.py                   |       51 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_research.py                        |       41 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_shell\_guards.py                   |       95 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_skill\_guard.py                    |      172 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_startup\_blocks.py                 |      142 |        0 |        2 |        0 |    100% |           |
| tests/test\_plugins\_tool\_usage.py                     |       68 |        0 |        8 |        0 |    100% |           |
| tests/test\_readme\_matrix.py                           |       41 |        0 |        6 |        0 |    100% |           |
| tests/test\_registry.py                                 |       49 |        5 |        0 |        0 |     90% |24, 30, 40, 44, 68 |
| tests/test\_research\_tracker.py                        |       50 |        0 |        0 |        0 |    100% |           |
| tests/test\_response.py                                 |      200 |        0 |        0 |        0 |    100% |           |
| tests/test\_retrospective\_tracker.py                   |       78 |        0 |       10 |        0 |    100% |           |
| tests/test\_skill\_tracker.py                           |       86 |        0 |        8 |        0 |    100% |           |
| tests/test\_state.py                                    |       67 |        0 |        4 |        0 |    100% |           |
| tests/test\_state\_jsonfile.py                          |       69 |        0 |        6 |        0 |    100% |           |
| tests/test\_state\_paths.py                             |       45 |        0 |        0 |        0 |    100% |           |
| tests/test\_state\_tool\_usage.py                       |       20 |        0 |        4 |        0 |    100% |           |
| tests/test\_turns.py                                    |       57 |        1 |        6 |        0 |     98% |        22 |
| tests/test\_uninstall.py                                |       54 |        0 |        0 |        0 |    100% |           |
| tests/test\_user\_install.py                            |       53 |        0 |        4 |        0 |    100% |           |
| tests/test\_workspace.py                                |       80 |        0 |        4 |        0 |    100% |           |
| **TOTAL**                                               | **14886** |  **212** | **1856** |  **122** | **98%** |           |


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