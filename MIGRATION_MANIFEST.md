# MIGRATION_MANIFEST

- source_repository: `aidenkael/EcommerceSkills`
- source_tag: `profit-legacy-freeze-20260728-r2`
- source_commit: `d0c07d374c9ee61926de9cd3e01b8c35260c8e5c`
- target_branch: `migration/r2-baseline`

所有来源均从固定 R2 标签提取。审计副本放在 `migration_sources/r2/`；可执行适配代码只放在 `src/profit_accounting_26/`。旧 Tkinter UI 不迁移。

## 迁移文件

| R2 来源 | 分类 | 审计副本 | 2.6 目标 | SHA256 | 说明 |
|---|---|---|---|---|---|
| `Profit accounting-Auto/calculation/profit.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/calculation/profit.py` | `src/profit_accounting_26/engines/profit/core.py` | `89f9ffb3001fb26047c684958d5207f55f09d06de78f4993a9859efb3d94641e` | 保留正算与反推边界，移除 UI 依赖 |
| `Profit accounting-Auto/calculation/logistics.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/calculation/logistics.py` | `src/profit_accounting_26/engines/logistics/core.py` | `1e0b1de6a40c6830b7161d88d4880b07baf19e940097ad2260db303155c7f37f` | 仅保留费用适配层，不平行维护上游算法 |
| `Profit accounting-Auto/calculation/profit_adjustments.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/calculation/profit_adjustments.py` | `src/profit_accounting_26/domain/rules.py` | `4ae5d0148dadd3547024c2b63ab78fcb9ac3b476d53d28bf61cca3b20f1e7585` | 可配置调整规则，不硬编码补贴 |
| `Profit accounting-Auto/calculation/rules.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/calculation/rules.py` | `src/profit_accounting_26/domain/rules.py` | `3752af24fa0f969ef04feeb7dfa77f4fe4dcf72f23783108d25da79341e6ff3c` | 保留规则启停、归档和生命周期语义 |
| `Profit accounting-Auto/config/config_manager.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/config/config_manager.py` | `src/profit_accounting_26/application/settings_service.py` | `6ffd50577a4fb0659f5ee85552c18eb0d0910c3f76836214ce4c57f54ce36bb3` | 原子 JSON 设置读写 |
| `Profit accounting-Auto/config/forwarder_manager.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/config/forwarder_manager.py` | `src/profit_accounting_26/application/settings_service.py` | `a1bd99757ef8f4bd30b28a99c376d59a04a66260419df1ab14fbe7abb9f67f0d` | 稳定 ID、启停、归档与恢复 |
| `Profit accounting-Auto/config/profit_adjustment_manager.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/config/profit_adjustment_manager.py` | `src/profit_accounting_26/domain/rules.py` | `83962cdd00badb99796cfa53c2f693d86cedabeffb5716821e023a5a7a230029` | 规则持久化语义来源 |
| `Profit accounting-Auto/database/db_manager.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/database/db_manager.py` | `src/profit_accounting_26/storage/sqlite_store.py` | `f946f8f2e03ed2c1c6967b530c77d1e79a697c2393fbc0b32740552eb3f9f7a2` | 新项目独立 SQLite schema，不连接旧库 |
| `Profit accounting-Auto/image_intake/image_types.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/image_intake/image_types.py` | `src/profit_accounting_26/domain/models.py` | `ca24a035c92cca742bef281ada226a4915d460d1bd14f99f0385f3ff32ce89be` | 收敛为三类图片 |
| `Profit accounting-Auto/image_intake/result_models.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/image_intake/result_models.py` | `src/profit_accounting_26/domain/models.py` | `fefcfc99d8d0f7262b47f36b3afdeb221c3869aba9804b7528db8d048fee3233` | AI/人工/系统/实际四类值分层 |
| `Profit accounting-Auto/image_intake/intake_service.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/image_intake/intake_service.py` | `src/profit_accounting_26/application/image_session.py` | `941f925c13a240239d5272c792cbe790a3f12c26e6cf72f90d496bfdcbdb95df` | 临时会话、哈希和导入基础 |
| `Profit accounting-Auto/image_intake/intake_controller.py` | REFERENCE_ONLY | `migration_sources/r2/Profit accounting-Auto/image_intake/intake_controller.py` | `-` | `054bb9d347ae8673f049ba1fc73554d787b38e951a6708b0b7c13a491fd4fe3d` | Tkinter 控制器不迁移 |
| `Profit accounting-Auto/image_intake/extractors/common.py` | REFERENCE_ONLY | `migration_sources/r2/Profit accounting-Auto/image_intake/extractors/common.py` | `-` | `028d7d24d70720722d77aca37dca3f2f23caa28c59fbf070c39c4269ce98aa76` | 提取经验留档，正式识别由外部视觉 AI |
| `Profit accounting-Auto/image_intake/extractors/dimension_extractor.py` | REFERENCE_ONLY | `migration_sources/r2/Profit accounting-Auto/image_intake/extractors/dimension_extractor.py` | `-` | `66abe48bdf2544fd398c07527b4c98fccc027d74f158d98545183de98ec5e0ec` | 离线参考，不主导正式 UI |
| `Profit accounting-Auto/image_intake/extractors/shein_price_extractor.py` | REFERENCE_ONLY | `migration_sources/r2/Profit accounting-Auto/image_intake/extractors/shein_price_extractor.py` | `-` | `b7b33487940d64605b621a0c280af5c043a0aa75faa63e254a29ddf50c0f3c90` | SHEIN 核价改为人工输入 |
| `Profit accounting-Auto/image_intake/extractors/cost_shipping_extractor.py` | REFERENCE_ONLY | `migration_sources/r2/Profit accounting-Auto/image_intake/extractors/cost_shipping_extractor.py` | `-` | `5b5d2379c69b4e2988df78e4941cb80ce7ad5e842f92ad61d0d43693c6205601` | 离线参考 |
| `Profit accounting-Auto/tests/test_profit.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/tests/test_profit.py` | `tests/profit/` | `d5a34da218085356dd1e51c9ff4fb61804225af16b703cc3e5227885aa2237b7` | 迁移边界测试 |
| `Profit accounting-Auto/tests/test_logistics.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/tests/test_logistics.py` | `tests/logistics/` | `c3a84db6ac05262b506a242d902d235557829605b8eb72c5fb98a171c94e3763` | 费用拆分测试 |
| `Profit accounting-Auto/tests/test_profit_adjustments.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/tests/test_profit_adjustments.py` | `tests/profit/test_adjustments.py` | `411d64daed5051714fc90d1de83986f7436288e9bc3f08c2b285288960558668` | 规则触发测试 |
| `Profit accounting-Auto/tests/test_unlimited_forwarders.py` | ADAPT | `migration_sources/r2/Profit accounting-Auto/tests/test_unlimited_forwarders.py` | `tests/logistics/test_logistics_core.py` | `0bbbca2c22abeebe4453a82f2ea340eb02d2b2bf37d8a054be61758569dc1556` | 动态货代测试 |
| `Profit accounting-Auto/docs/Development rules-1.5.md` | DOCUMENT_ONLY | `migration_sources/r2/Profit accounting-Auto/docs/Development rules-1.5.md` | `migration_sources/r2/` | `2f4816c5c647da8e55856ae637b4d88ceb1e5d736d3ed01f7ec109d19e2a9282` | 旧项目冻结来源，不指导 2.6 |
| `logistics-cost-skill-2.0/logistics_cost/calculator.py` | KEEP | `migration_sources/r2/logistics-cost-skill-2.0/logistics_cost/calculator.py` | `migration_sources/r2/` | `fc6faae0fb387ac974153612145b3595840e12a1ab828756c18bcda7d248bf9e` | 物流唯一上游冻结核心快照 |
| `logistics-cost-skill-2.0/logistics_cost/estimator.py` | ADAPT | `migration_sources/r2/logistics-cost-skill-2.0/logistics_cost/estimator.py` | `migration_sources/r2/` | `b03d28ce2fbf2432c9771f27c9c57a41c853082c4285a84349807b435027b7f2` | 后续通过正式版本包接入 |
| `logistics-cost-skill-2.0/logistics_cost/weight_rules.py` | KEEP | `migration_sources/r2/logistics-cost-skill-2.0/logistics_cost/weight_rules.py` | `migration_sources/r2/` | `36149a460057d173267e56c9070bad604074870689b472c078b4cb3a14f6b21e` | R2 重量规则快照 |
| `logistics-cost-skill-2.0/logistics_cost/ai_schema.py` | ADAPT | `migration_sources/r2/logistics-cost-skill-2.0/logistics_cost/ai_schema.py` | `migration_sources/r2/` | `4c67745c27738718b7af6474d26c3c48cf2a56b4e8fad8f4e302c3f922320726` | AI schema 来源快照 |
| `logistics-cost-skill-2.0/config/logistics_config.json` | KEEP | `migration_sources/r2/logistics-cost-skill-2.0/config/logistics_config.json` | `config/logistics_source.json` | `9bb9e1d78798d1e1412de5dec2dfc351f67135a73bc976a20c39905b740cf2b8` | 配置格式来源；默认值保持可修改 |
| `logistics-cost-skill-2.0/tests/test_integration.py` | ADAPT | `migration_sources/r2/logistics-cost-skill-2.0/tests/test_integration.py` | `tests/logistics/` | `059e7edf2f7c5b74e3fa8db75fc48816f7abb0c7c3947b98bc7f45add2ea3c73` | 兼容测试来源 |
| `logistics-cost-skill-2.0/tests/test_replay_validation.py` | ADAPT | `migration_sources/r2/logistics-cost-skill-2.0/tests/test_replay_validation.py` | `tests/logistics/` | `bc1a3f896a2d8d29ef3e5f30cc50679b0eff9751bc796e759c7449e3ec4833b8` | 回放验证来源 |
| `logistics-cost-skill-2.0/scripts/phase5_replay.py` | ADAPT | `migration_sources/r2/logistics-cost-skill-2.0/scripts/phase5_replay.py` | `migration_sources/r2/` | `d70d2eeb5068e6a1032cd14c1a725801fe415643af78371de12d647adc689981` | 回放工具来源快照 |
| `logistics-cost-skill-2.0/scripts/phase1_clean_data.py` | ADAPT | `migration_sources/r2/logistics-cost-skill-2.0/scripts/phase1_clean_data.py` | `migration_sources/r2/` | `2a4d7b60766944f0119008cfbc89563158aaa782757fdf8fa31910f6f3564e50` | 清洗工具来源快照 |
| `docs/LEGACY_FREEZE.md` | DOCUMENT_ONLY | `migration_sources/r2/docs/LEGACY_FREEZE.md` | `migration_sources/r2/` | `2a30ba6548dcca812db0fa4524a2a452b3be4341692f87cdb9822d650c02857c` | 冻结声明 |
| `docs/MIGRATION_SOURCE_MANIFEST.md` | DOCUMENT_ONLY | `migration_sources/r2/docs/MIGRATION_SOURCE_MANIFEST.md` | `migration_sources/r2/` | `9da68e67cbf853ee22ef4952eafa06047448d2d699055fcd77e62b0144bea90a` | R2 迁移索引 |
| `docs/BRANCH_MERGE_MANIFEST.md` | DOCUMENT_ONLY | `migration_sources/r2/docs/BRANCH_MERGE_MANIFEST.md` | `migration_sources/r2/` | `13ec05bda5363c082de590911e77b115d74bdf759cb88950c176056b2426cd9b` | R2 合并审计 |
| `review_packages/profit-legacy-freeze/final_report.md` | DOCUMENT_ONLY | `migration_sources/r2/review_packages/profit-legacy-freeze/final_report.md` | `migration_sources/r2/` | `d236c4b01de5fa16640176f05d815df88f55014b1a2e9a8fd4111b633d9b6450` | 冻结测试记录 |
| `logistics-cost-skill-2.0/docs/LOGISTICS_MAINTENANCE_WORKFLOW.md` | DOCUMENT_ONLY | `migration_sources/r2/logistics-cost-skill-2.0/docs/LOGISTICS_MAINTENANCE_WORKFLOW.md` | `migration_sources/r2/` | `9284f0d4c0f9989b79c415903579649778d988f474980c36b646534a778acbe5` | 物流维护唯一流程 |

## 校准与示例

| R2 来源 | 分类 | 目标 | SHA256 |
|---|---|---|---|
| `logistics-cost-skill-2.0/archive/calibration/calibration_samples.json` | KEEP | `calibration/r2/calibration_samples.json` | `1a868d0aa501808d83762b97af91394c752e7ad5ecd777acd4879585ce1cd1a9` |
| `logistics-cost-skill-2.0/archive/calibration/calibration_samples_cleaned_v1.json` | KEEP | `calibration/r2/calibration_samples_cleaned_v1.json` | `04f9e59dd45a4abbdeee535305638a808ec8839ff6ca2ce231752509559d4e20` |
| `logistics-cost-skill-2.0/archive/calibration/calibration_samples_round_02.json` | KEEP | `calibration/r2/calibration_samples_round_02.json` | `e1918ce27812c5beb4dc5ce92657c44d2168f202a6b53e1351741cebcaa5b688` |
| `logistics-cost-skill-2.0/examples/alloy_stone_brooch_ai.json` | KEEP | `calibration/r2/examples/alloy_stone_brooch_ai.json` | `a5881c4ca02a717858d9fbf401a3ae186ac54a361829aa41dcc2cc8e2336059f` |
| `logistics-cost-skill-2.0/examples/angel_wing_brooch_ai.json` | KEEP | `calibration/r2/examples/angel_wing_brooch_ai.json` | `38b157027d9faf744aeeb459ff69f15a1224b429ce6bb1a0c964148c0bff7a05` |
| `logistics-cost-skill-2.0/examples/apple_compact_mirror_ai.json` | KEEP | `calibration/r2/examples/apple_compact_mirror_ai.json` | `0ab112fc9adc45137a663429200d81db2f5c1c16c70e68318d81ac44b87ce352` |
| `logistics-cost-skill-2.0/examples/apple_smoothie_squishy_ai.json` | KEEP | `calibration/r2/examples/apple_smoothie_squishy_ai.json` | `ef735da6e0f1ae5b1b51f4816ccb28c92c8e87d8bc19d33a5b460a9e8b08bd1a` |
| `logistics-cost-skill-2.0/examples/arm_sleeves_ai.json` | KEEP | `calibration/r2/examples/arm_sleeves_ai.json` | `16e46e63f4911e81c682904e9cc144056cf8dd0250ee5b91149211eafdb6da15` |
| `logistics-cost-skill-2.0/examples/aroma_diffuser_ai.json` | KEEP | `calibration/r2/examples/aroma_diffuser_ai.json` | `3c04526941fd4105034051af00e667063e93ff81114ce27cf65989d04ae73da4` |
| `logistics-cost-skill-2.0/examples/batman_cowl_mask_ai.json` | KEEP | `calibration/r2/examples/batman_cowl_mask_ai.json` | `c23b1de3a0f1d171ac4870579bfe53917f94c01e3157d166f94ce522fa6633cb` |
| `logistics-cost-skill-2.0/examples/bikini_swimsuit_set_ai.json` | KEEP | `calibration/r2/examples/bikini_swimsuit_set_ai.json` | `ba9aaa73c7885a4369c21ce95447c14ebe0da001449ee876488d07061ef007d7` |
| `logistics-cost-skill-2.0/examples/black_tabi_socks_ai.json` | KEEP | `calibration/r2/examples/black_tabi_socks_ai.json` | `7270d4544f04a4d45171475cf6362abecd207a7bb7656c014fec7d798eb6fab1` |
| `logistics-cost-skill-2.0/examples/blue_crew_socks_ai.json` | KEEP | `calibration/r2/examples/blue_crew_socks_ai.json` | `f8a2233bd6aaf03fe9767d4d53f255e298a6c1ba3ee03a0391539e272a8e1723` |
| `logistics-cost-skill-2.0/examples/body_chain_no_pierce_ai.json` | KEEP | `calibration/r2/examples/body_chain_no_pierce_ai.json` | `ebca692fb029f66e82a4d7430b7ec8bdf0b96d117ffa41b9f9ee76853661d51e` |
| `logistics-cost-skill-2.0/examples/brass_maneki_neko_ai.json` | KEEP | `calibration/r2/examples/brass_maneki_neko_ai.json` | `c32a7af6703527582c5b28fed4ae40289f8a496697bfb006acc041d575184455` |
| `logistics-cost-skill-2.0/examples/brush_set_ai.json` | KEEP | `calibration/r2/examples/brush_set_ai.json` | `fa9fa6bf7df47faff3cb827dd8e5ed972c1700bf77e4cb7cf45632577fd23688` |
| `logistics-cost-skill-2.0/examples/camera_strap_ai.json` | KEEP | `calibration/r2/examples/camera_strap_ai.json` | `7ba045fdf32c156c2f7c0fae713ac34641b1f8920a54f7adaaa0c54305770ee9` |
| `logistics-cost-skill-2.0/examples/cotton_skull_cap_ai.json` | KEEP | `calibration/r2/examples/cotton_skull_cap_ai.json` | `75d944e6df31f971969a4a7d1cbf0538426b11855dbbf7b8992129c1aa5cd054` |
| `logistics-cost-skill-2.0/examples/cream_tabisocks_5pack_ai.json` | KEEP | `calibration/r2/examples/cream_tabisocks_5pack_ai.json` | `31e6882e067c88ab0eab065285f1cfa71ee6374c08d6c9dd61fe9f0f29d6ebad` |
| `logistics-cost-skill-2.0/examples/dual_head_makeup_brush_set_F4E6_ai.json` | KEEP | `calibration/r2/examples/dual_head_makeup_brush_set_F4E6_ai.json` | `86e1f3cabb64c0cd3d6037158825181c558d57f67c72a49403a4ea361e16affc` |
| `logistics-cost-skill-2.0/examples/evening_clutch_ai.json` | KEEP | `calibration/r2/examples/evening_clutch_ai.json` | `f0e4714982174f6aeb63ab6387d748f5d4360863eed8627514f5e3eff5e56c75` |
| `logistics-cost-skill-2.0/examples/five_toe_socks_ai.json` | KEEP | `calibration/r2/examples/five_toe_socks_ai.json` | `572f82c5068dbb47be94284b99d52e03b198889aeb7e9fb1f9a889757489a415` |
| `logistics-cost-skill-2.0/examples/flat_top_cap_ai.json` | KEEP | `calibration/r2/examples/flat_top_cap_ai.json` | `443402c6f5d93cfaacc63d91fc30fdca486e32b6b7729ceac33a3f26bb7a5a89` |
| `logistics-cost-skill-2.0/examples/folding_fan_ai.json` | KEEP | `calibration/r2/examples/folding_fan_ai.json` | `5292718056904f5b9fb2bb462f663499f2a8d599e312e9383ead48db4fab8c66` |
| `logistics-cost-skill-2.0/examples/football_keychain_set_ai.json` | KEEP | `calibration/r2/examples/football_keychain_set_ai.json` | `b6603b4f44d5a6ed4d3d764e5c2d1e2a0bad6b3b0d0f925bec84f64a60975902` |
| `logistics-cost-skill-2.0/examples/furniture_corner_protectors_ai.json` | KEEP | `calibration/r2/examples/furniture_corner_protectors_ai.json` | `63ad0d18bebbe0181909f21daf0cba97e287bcee0933b32fb81ea10caf269600` |
| `logistics-cost-skill-2.0/examples/gaia_figurine_ai.json` | KEEP | `calibration/r2/examples/gaia_figurine_ai.json` | `6c43c08d1786192af03fd1715d8951255e56f1e0a10c7fd2c3bee7cb7b0bd097` |
| `logistics-cost-skill-2.0/examples/ganesha_ai.json` | KEEP | `calibration/r2/examples/ganesha_ai.json` | `4339bb4a0949fd1f8ccf89e8930fa08c595ac6e94c05912484cefc65c0bd5b26` |
| `logistics-cost-skill-2.0/examples/garlic_grinder_ai.json` | KEEP | `calibration/r2/examples/garlic_grinder_ai.json` | `11b9cdfffd41c7419301b853bdde764360779f6e13c244bea34731cdd9c0577f` |
| `logistics-cost-skill-2.0/examples/glass_apple_decoration_ai.json` | KEEP | `calibration/r2/examples/glass_apple_decoration_ai.json` | `9ddb8f7da2c79e25308d7be7ae413c7a92e62bbe85f222372f0a5cc333b5a2a3` |
| `logistics-cost-skill-2.0/examples/gothic_lace_arm_gloves_ai.json` | KEEP | `calibration/r2/examples/gothic_lace_arm_gloves_ai.json` | `e84842638cd3b69d470d6824eeaf907dfd8b1eb860f2ed89b10544a2ea9e93b3` |
| `logistics-cost-skill-2.0/examples/greca_belt_ai.json` | KEEP | `calibration/r2/examples/greca_belt_ai.json` | `a1707e7972d12f46a748d034b38d49bbedbb81e6dc7046e356be22fc28a4043a` |
| `logistics-cost-skill-2.0/examples/greca_belt_v2.json` | KEEP | `calibration/r2/examples/greca_belt_v2.json` | `6db9b794ff7c519452a0c5df5c0cc7094be106b68df96f1a256965ab801bb582` |
| `logistics-cost-skill-2.0/examples/gym_workout_gloves_ai.json` | KEEP | `calibration/r2/examples/gym_workout_gloves_ai.json` | `67356feeeb8e1acb4cf57f19c8b29e056e7b7bcda1b7eeb947211bf3e1640bdd` |
| `logistics-cost-skill-2.0/examples/hair_stick_5pack_ai.json` | KEEP | `calibration/r2/examples/hair_stick_5pack_ai.json` | `a28da2bf92208cbb0aa6b905204fa4888ad40b7d05e209cd06d5db1c4369e8bd` |
| `logistics-cost-skill-2.0/examples/hanging_hand_towel_ai.json` | KEEP | `calibration/r2/examples/hanging_hand_towel_ai.json` | `3bbfbcee528d3c0bfcd29a6dcac78cd9480e0f14923c07268028a2cd7c568463` |
| `logistics-cost-skill-2.0/examples/houndstooth_knee_socks_ai.json` | KEEP | `calibration/r2/examples/houndstooth_knee_socks_ai.json` | `b069c91d2c2d95bf17569b34c01415fc30a8a175b9dd4e9101171195f7f6f1b3` |
| `logistics-cost-skill-2.0/examples/kazoo_metal_instrument_ai.json` | KEEP | `calibration/r2/examples/kazoo_metal_instrument_ai.json` | `89e32adec354ef05a28094ad6785959c759e9022335d86a6eb9b6282c22504bb` |
| `logistics-cost-skill-2.0/examples/latex_batman_cowl_mask_ai.json` | KEEP | `calibration/r2/examples/latex_batman_cowl_mask_ai.json` | `fded0359d482532f23ad3708da7a4fcc82da08c3498593ca6f0f53654693d515` |
| `logistics-cost-skill-2.0/examples/long_wallet_phone_combo_ai.json` | KEEP | `calibration/r2/examples/long_wallet_phone_combo_ai.json` | `45f81c147b7c1394106c3fe6a492bc59f8de69caa1a1247750eadebff2a4c0e3` |
| `logistics-cost-skill-2.0/examples/malt_sugar_ball_ai.json` | KEEP | `calibration/r2/examples/malt_sugar_ball_ai.json` | `61e79b3aa3a258cb2db6abe46d524a49f85eaec4bddb745858f3855d7459eafe` |
| `logistics-cost-skill-2.0/examples/mesh_cycling_skull_cap_ai.json` | KEEP | `calibration/r2/examples/mesh_cycling_skull_cap_ai.json` | `676d01619207ec886a297898da5346692ee748a1239c812883373c20a8b62db2` |
| `logistics-cost-skill-2.0/examples/mini_strawberry_backpack_ai.json` | KEEP | `calibration/r2/examples/mini_strawberry_backpack_ai.json` | `58adf390a898fd2440316186f61f0b9131be38a3334e4d9eb8838b205433074b` |
| `logistics-cost-skill-2.0/examples/mlp_purple_curly_wig_ai.json` | KEEP | `calibration/r2/examples/mlp_purple_curly_wig_ai.json` | `3c70bcdd9d2990c2c40cf6cbeb033439a3231b18e1107b2238c417cc9fa030c3` |
| `logistics-cost-skill-2.0/examples/nail_art_brush_ai.json` | KEEP | `calibration/r2/examples/nail_art_brush_ai.json` | `f7834bc5677be1fdf39052ae01f79d96962333f78cf4665025861f7002b96e2d` |
| `logistics-cost-skill-2.0/examples/painthandle_ai.json` | KEEP | `calibration/r2/examples/painthandle_ai.json` | `3bd67416515513257a4f15337b7d6aafb965ef16fd1cecbcb9a973b9efff7b36` |
| `logistics-cost-skill-2.0/examples/pet_bandana_ai.json` | KEEP | `calibration/r2/examples/pet_bandana_ai.json` | `70e6e803da249643dda258484c1d8a7bc520812877bd03955511ddc7e4402994` |
| `logistics-cost-skill-2.0/examples/pet_car_safety_belt_ai.json` | KEEP | `calibration/r2/examples/pet_car_safety_belt_ai.json` | `270a8b4fa786d90b1177d349ac36b0f4ef6ad5ed36dac27beb72a96f20af0ad6` |
| `logistics-cost-skill-2.0/examples/plush_wing_clip_ai.json` | KEEP | `calibration/r2/examples/plush_wing_clip_ai.json` | `994e029f85c3ad93435257ec20d64de9b0ed1d1214cbb2b489b79bb6e5628962` |
| `logistics-cost-skill-2.0/examples/pu_flower_bag_charm_ai.json` | KEEP | `calibration/r2/examples/pu_flower_bag_charm_ai.json` | `610154e23c94e9471336f6eb056cf4de8c4796a076dd6076e32832570b2e7d8f` |
| `logistics-cost-skill-2.0/examples/pu_small_chain_shoulder_bag_ai.json` | KEEP | `calibration/r2/examples/pu_small_chain_shoulder_bag_ai.json` | `83aea41a54c3706b4755df718576fd4bd09f52766f750c3f54cc503646ecac5c` |
| `logistics-cost-skill-2.0/examples/ribbed_arm_sleeves_ai.json` | KEEP | `calibration/r2/examples/ribbed_arm_sleeves_ai.json` | `404307b9ff83ccaa250fb8068dc2a58d6c7727eb2662d2bd22c27a3b3c78e669` |
| `logistics-cost-skill-2.0/examples/satin_scrunchie_ai.json` | KEEP | `calibration/r2/examples/satin_scrunchie_ai.json` | `445966e5ee10d73a6505d9912e9896cc7cba9176a19ce7ec843615480289d60e` |
| `logistics-cost-skill-2.0/examples/satin_sleep_cap_ai.json` | KEEP | `calibration/r2/examples/satin_sleep_cap_ai.json` | `5fe74c737a964e6ce202ff7989abf696f3a7ed083a9e81e92fafc9c668e4efce` |
| `logistics-cost-skill-2.0/examples/seamless_bandeau_ai.json` | KEEP | `calibration/r2/examples/seamless_bandeau_ai.json` | `73c5bdc405aa0013408d7872d2418ee5a696f3275ce24268f9d31b589fe46dd0` |
| `logistics-cost-skill-2.0/examples/sheer_pantyhose_ai.json` | KEEP | `calibration/r2/examples/sheer_pantyhose_ai.json` | `1a0172dc9473af860f56d59b7355d0a89805f2d9def69847d94caf963dddb42f` |
| `logistics-cost-skill-2.0/examples/shell_evening_clutch_ai.json` | KEEP | `calibration/r2/examples/shell_evening_clutch_ai.json` | `bac5185ddc76fb7b300d3bc779fcb63a321d3781992d5a84b1986cbf745d7b24` |
| `logistics-cost-skill-2.0/examples/silicone_bear_ice_mold_ai.json` | KEEP | `calibration/r2/examples/silicone_bear_ice_mold_ai.json` | `27d2300cf7cfd27068490779b7b7a352444549fe839aa7dfe3363b2fdbec45d0` |
| `logistics-cost-skill-2.0/examples/silicone_door_stopper_ai.json` | KEEP | `calibration/r2/examples/silicone_door_stopper_ai.json` | `2c81c68c29d91c913fdf466bbb387f5ed7611a0227eb51e8cc5cc3af9e35e1fa` |
| `logistics-cost-skill-2.0/examples/silicone_earplugs_pair_ai.json` | KEEP | `calibration/r2/examples/silicone_earplugs_pair_ai.json` | `83f8e29a8f5638937c3d8ae1bc6a3cd6647bb8e5e80c4c36d8e3c287454e57e6` |
| `logistics-cost-skill-2.0/examples/smart_temp_coffee_cup_ai.json` | KEEP | `calibration/r2/examples/smart_temp_coffee_cup_ai.json` | `003ad8d1a93268321f429534df9ee86a879ec44bec96b7c295e31d6e68a398de` |
| `logistics-cost-skill-2.0/examples/snowflake_hair_clip_ai.json` | KEEP | `calibration/r2/examples/snowflake_hair_clip_ai.json` | `c5572620f19269ebe3680fe268cf61f00d8e6fd25ba4b354375fe4042c73d874` |
| `logistics-cost-skill-2.0/examples/socks_ai.json` | KEEP | `calibration/r2/examples/socks_ai.json` | `2f0b28f79ba9753b861d86e3bb74e61a0f3527f2b21b8de70c218039a13b8a1f` |
| `logistics-cost-skill-2.0/examples/split_toe_socks_ai.json` | KEEP | `calibration/r2/examples/split_toe_socks_ai.json` | `08cd8619e87ba70e89ef4040281ea6fc18b2e2da41155ed1cf776b87d6d46f50` |
| `logistics-cost-skill-2.0/examples/thin_wallet_coin_purse_ai.json` | KEEP | `calibration/r2/examples/thin_wallet_coin_purse_ai.json` | `3e04815036e9cb94b56a604714d4e8f4421cfa01735a32e90d5c44b2cf466b4e` |
| `logistics-cost-skill-2.0/examples/two_toe_socks_5pack_ai.json` | KEEP | `calibration/r2/examples/two_toe_socks_5pack_ai.json` | `d9925ccfc53a2f0e937902fb857d24362c42b3f2098bf3b9b39f2a8c00fa36ec` |
| `logistics-cost-skill-2.0/examples/waterproof_phone_pouch_ai.json` | KEEP | `calibration/r2/examples/waterproof_phone_pouch_ai.json` | `ca1c92b29542cace0f2f8885da4bbcfa7118323cc92514e8d8bc9fd20cd2eb50` |
| `logistics-cost-skill-2.0/examples/white_two_toe_socks_ai.json` | KEEP | `calibration/r2/examples/white_two_toe_socks_ai.json` | `405b799f5e246084bef420e73eeca10e86e5a08ef4d1b86e40ae81f89651872b` |
| `logistics-cost-skill-2.0/examples/window_scraper_ai.json` | KEEP | `calibration/r2/examples/window_scraper_ai.json` | `8ecd2207c57cff1621d62e14c70cffb5460a101fe3ca3508c9dc123d2dd6e6ac` |

## 明确排除

- 旧 Tkinter 主窗口、ProductPage、历史页和 OCR 对话框的可执行迁移；
- 旧 SQLite 真实数据库、真实图片和测试会话；
- `.venv`、缓存、构建产物、Token、Cookie、API Key、浏览器 Profile 和压缩包；
- `airpods_case`、`folding_sunglasses`、`seatbelt_extender` 三份下一轮校准数据。
