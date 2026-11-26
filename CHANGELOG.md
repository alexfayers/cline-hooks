# Changelog

## [0.5.0](https://github.com/alexfayers/cline-hooks/compare/v0.4.0...v0.5.0) (2026-11-26)


### Features

* drop pi hook state once a rewind, /tree or compaction removes its point from the context ([#256](https://github.com/alexfayers/cline-hooks/issues/256)) ([0d99c02](https://github.com/alexfayers/cline-hooks/commit/0d99c0228129f832953de791065432f4b5eeb1f7))
* keep state under the shared llm-prompts root, copied once from the old folder ([#254](https://github.com/alexfayers/cline-hooks/issues/254)) ([910a39a](https://github.com/alexfayers/cline-hooks/commit/910a39a3277c1c73b6d4cf31ed7cfddac790e5a8))
* report ahead/behind counts against the cached upstream in session-start git context ([#258](https://github.com/alexfayers/cline-hooks/issues/258)) ([92447ab](https://github.com/alexfayers/cline-hooks/commit/92447abdeeb39bd3335361cc0e95466413f04771))


### Bug Fixes

* cap hook memory by data segment instead of address space ([#259](https://github.com/alexfayers/cline-hooks/issues/259)) ([52cffc2](https://github.com/alexfayers/cline-hooks/commit/52cffc26740de14ef90e868e450481b63b976f4f))

## [0.4.0](https://github.com/alexfayers/cline-hooks/compare/v0.3.2...v0.4.0) (2026-11-26)


### Features

* block inline python and node scripts that parse JSON from stdin ([#253](https://github.com/alexfayers/cline-hooks/issues/253)) ([8da0348](https://github.com/alexfayers/cline-hooks/commit/8da03486e29726aa2f85c86259f48bcf20ac55ab))
* give an oversized recursive search the workspace as its path ([#246](https://github.com/alexfayers/cline-hooks/issues/246)) ([74264d2](https://github.com/alexfayers/cline-hooks/commit/74264d229930fe78af4de55d38d076b8dfafc815))
* give pi bash calls a default timeout ([#242](https://github.com/alexfayers/cline-hooks/issues/242)) ([82a28d6](https://github.com/alexfayers/cline-hooks/commit/82a28d62f00cb8e7f50f67cb31e7cf74efbee631))
* move a fork's foreground watch to the background ([#251](https://github.com/alexfayers/cline-hooks/issues/251)) ([1f5d370](https://github.com/alexfayers/cline-hooks/commit/1f5d370824bcad3897fa1f56a2a8137586de8cd0))
* redirect a filtered build's output to a log instead of blocking ([#247](https://github.com/alexfayers/cline-hooks/issues/247)) ([2897a0f](https://github.com/alexfayers/cline-hooks/commit/2897a0fe596586fcdf86a389b408dafbbe9a50e8))
* redirect a writer's edit in the primary checkout to its worktree ([#248](https://github.com/alexfayers/cline-hooks/issues/248)) ([5abcb4b](https://github.com/alexfayers/cline-hooks/commit/5abcb4bc7fc2a75b92a0e454c1e63a42bc07d6d6))
* run a call and add its skill text once instead of blocking ([#245](https://github.com/alexfayers/cline-hooks/issues/245)) ([92577f9](https://github.com/alexfayers/cline-hooks/commit/92577f90fa5a92153a7750b172b8f3928cb4681b))
* send the lead's test runs, debugging and large reads to a fork ([#252](https://github.com/alexfayers/cline-hooks/issues/252)) ([6efee69](https://github.com/alexfayers/cline-hooks/commit/6efee69e54624617501709f0287e3f19bceedc02))


### Bug Fixes

* let the delegation note allow a small fix inline ([#244](https://github.com/alexfayers/cline-hooks/issues/244)) ([952457b](https://github.com/alexfayers/cline-hooks/commit/952457b9476facbaaa1aaf03cc7b406f815a51ca))
* show a skill note once whether or not it has the reminder prefix ([#250](https://github.com/alexfayers/cline-hooks/issues/250)) ([9e82283](https://github.com/alexfayers/cline-hooks/commit/9e822837ce7329e0a0b9aeb9e1185e633381a7ca))


### Miscellaneous Chores

* sync shared files from llm-prompts-ci ([#230](https://github.com/alexfayers/cline-hooks/issues/230)) ([faa534d](https://github.com/alexfayers/cline-hooks/commit/faa534d7762ee5f84d2a3befe17d7d34d3793d4b))

## [0.3.2](https://github.com/alexfayers/cline-hooks/compare/v0.3.1...v0.3.2) (2026-11-25)


### Bug Fixes

* run hooks without a memory cap where macOS rejects it ([#226](https://github.com/alexfayers/cline-hooks/issues/226)) ([a083816](https://github.com/alexfayers/cline-hooks/commit/a08381688214fd6dad0e5d68b6d369477f2e0b53))


### Miscellaneous Chores

* **deps:** update all non-major dependencies ([#227](https://github.com/alexfayers/cline-hooks/issues/227)) ([419f743](https://github.com/alexfayers/cline-hooks/commit/419f7437153812f20a06029273dcf5703cc65e2f))

## [0.3.1](https://github.com/alexfayers/cline-hooks/compare/v0.3.0...v0.3.1) (2026-11-25)


### Bug Fixes

* cap hook memory, CPU time and run time ([#203](https://github.com/alexfayers/cline-hooks/issues/203)) ([43d19e8](https://github.com/alexfayers/cline-hooks/commit/43d19e8dbd8a1ddcc6d1c3c6b69fbe68d0caef3d))


### Performance Improvements

* **pi:** stream the transcript when finding the active branch ([#204](https://github.com/alexfayers/cline-hooks/issues/204)) ([a0daf35](https://github.com/alexfayers/cline-hooks/commit/a0daf35e382a884bab15753dc46554912b29a732))

## [0.3.0](https://github.com/alexfayers/cline-hooks/compare/v0.2.3...v0.3.0) (2026-11-24)


### Features

* add opencode 2.x frontend and bridge plugin ([#194](https://github.com/alexfayers/cline-hooks/issues/194)) ([2fcce78](https://github.com/alexfayers/cline-hooks/commit/2fcce78ecbebd8c8408353b87157448fb389aaec))


### Miscellaneous Chores

* **deps:** refresh fayers-configs source ([#223](https://github.com/alexfayers/cline-hooks/issues/223)) ([a86e916](https://github.com/alexfayers/cline-hooks/commit/a86e9168c6f4fac9325a948f6909c7d5f6219625))
* **deps:** update all non-major dependencies ([#219](https://github.com/alexfayers/cline-hooks/issues/219)) ([7d4c5d9](https://github.com/alexfayers/cline-hooks/commit/7d4c5d9177b888a409c9275f3c650e1cfa46307f))
* **deps:** update github actions ([#221](https://github.com/alexfayers/cline-hooks/issues/221)) ([09ad74e](https://github.com/alexfayers/cline-hooks/commit/09ad74ee1b22c2891d03a58d2f535f240e23e0eb))
* match the Biome schema to the locked version ([#222](https://github.com/alexfayers/cline-hooks/issues/222)) ([ce33e59](https://github.com/alexfayers/cline-hooks/commit/ce33e5963d9a27fe6dac69ae256d3dc0dca07eb4))

## [0.2.3](https://github.com/alexfayers/cline-hooks/compare/v0.2.2...v0.2.3) (2026-11-23)


### Miscellaneous Chores

* **deps:** lock file maintenance ([#214](https://github.com/alexfayers/cline-hooks/issues/214)) ([86341e9](https://github.com/alexfayers/cline-hooks/commit/86341e9dd3654336f06ecd9ddda0b5d5a55b72aa))

## [0.2.2](https://github.com/alexfayers/cline-hooks/compare/v0.2.1...v0.2.2) (2026-11-22)


### Miscellaneous Chores

* **deps:** update github actions ([#212](https://github.com/alexfayers/cline-hooks/issues/212)) ([3d28b99](https://github.com/alexfayers/cline-hooks/commit/3d28b9990f9fb9d45b9d849edf1cabd278c85ce5))

## [0.2.1](https://github.com/alexfayers/cline-hooks/compare/v0.2.0...v0.2.1) (2026-11-21)


### Performance Improvements

* **hooks:** read git context with plain git commands ([#205](https://github.com/alexfayers/cline-hooks/issues/205)) ([69a7893](https://github.com/alexfayers/cline-hooks/commit/69a7893f635137f07c7e19a4e1836e0534f69120))


### Miscellaneous Chores

* sync shared files from llm-prompts-ci ([#210](https://github.com/alexfayers/cline-hooks/issues/210)) ([625d44b](https://github.com/alexfayers/cline-hooks/commit/625d44bea71b0a609c43a17b8636ac959b21faa5))

## [0.2.0](https://github.com/alexfayers/cline-hooks/compare/v0.1.4...v0.2.0) (2026-11-20)


### Features

* ask subagents to request a replacement at 200k tokens ([#200](https://github.com/alexfayers/cline-hooks/issues/200)) ([8ce86ee](https://github.com/alexfayers/cline-hooks/commit/8ce86ee3012933f6431fe1cb36d169cb47027a80))

## [0.1.4](https://github.com/alexfayers/cline-hooks/compare/v0.1.3...v0.1.4) (2026-11-19)


### Bug Fixes

* set up logging only when the cline-hook command runs ([#198](https://github.com/alexfayers/cline-hooks/issues/198)) ([91497f7](https://github.com/alexfayers/cline-hooks/commit/91497f7f19242d293d1b3b4dbd40abd38759e29d))


### Miscellaneous Chores

* **deps:** update all non-major dependencies ([#199](https://github.com/alexfayers/cline-hooks/issues/199)) ([da04981](https://github.com/alexfayers/cline-hooks/commit/da049818cda9bce3e08ddeb748db8cebf32e081a))
* sync shared files from llm-prompts-ci ([#196](https://github.com/alexfayers/cline-hooks/issues/196)) ([6db2846](https://github.com/alexfayers/cline-hooks/commit/6db28468f4790500a5170e84eac977a2de5ebf65))

## [0.1.3](https://github.com/alexfayers/cline-hooks/compare/v0.1.2...v0.1.3) (2026-11-18)


### Bug Fixes

* **pi:** give forks their own identity so they keep the lead's skill reads ([#191](https://github.com/alexfayers/cline-hooks/issues/191)) ([8293e90](https://github.com/alexfayers/cline-hooks/commit/8293e90bdd8dc89c6951d078740c13f8b3d60e90))

## [0.1.2](https://github.com/alexfayers/cline-hooks/compare/v0.1.1...v0.1.2) (2026-11-17)


### Bug Fixes

* **pi:** send a pi-context writer's worktree as the hook cwd ([#187](https://github.com/alexfayers/cline-hooks/issues/187)) ([6b8c722](https://github.com/alexfayers/cline-hooks/commit/6b8c72271150d3703c3b0b05ed60cf2b5dac6915))


### Miscellaneous Chores

* **deps:** update all non-major dependencies ([#189](https://github.com/alexfayers/cline-hooks/issues/189)) ([fb77354](https://github.com/alexfayers/cline-hooks/commit/fb77354890b00d43dd3866a73de8d9b0adbd1632))
* sync shared files from llm-prompts-ci ([#188](https://github.com/alexfayers/cline-hooks/issues/188)) ([8c0d600](https://github.com/alexfayers/cline-hooks/commit/8c0d600b9369bf80b29ca292b230f67a041be8e1))

## [0.1.1](https://github.com/alexfayers/cline-hooks/compare/v0.1.0...v0.1.1) (2026-11-16)


### Miscellaneous Chores

* **deps:** lock file maintenance ([#185](https://github.com/alexfayers/cline-hooks/issues/185)) ([4b0edab](https://github.com/alexfayers/cline-hooks/commit/4b0edab341a66f91d38a4b12fbab784f62d432ef))
* **deps:** update all non-major dependencies ([#180](https://github.com/alexfayers/cline-hooks/issues/180)) ([d71fb45](https://github.com/alexfayers/cline-hooks/commit/d71fb459a31f48b4c731a790cf5225f3a9f90bb3))
* sync Copilot review rules from llm-prompts-ci ([#181](https://github.com/alexfayers/cline-hooks/issues/181)) ([250d69a](https://github.com/alexfayers/cline-hooks/commit/250d69a93125e857392e89774d4c548fb14055d6))
* sync shared files from llm-prompts-ci ([#182](https://github.com/alexfayers/cline-hooks/issues/182)) ([ad3488e](https://github.com/alexfayers/cline-hooks/commit/ad3488edb54e8e3fa5643c2d83dbd3baa4f2d665))
* sync shared files from llm-prompts-ci ([#184](https://github.com/alexfayers/cline-hooks/issues/184)) ([30d554f](https://github.com/alexfayers/cline-hooks/commit/30d554f44e0798074c31c7403697dfb8a1cc4194))
