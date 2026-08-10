# Changelog

## [0.9.0](https://github.com/FreezeManny/labops/compare/labops-v0.8.0...labops-v0.9.0) (2026-08-10)


### Features

* 30 pihole support ([#47](https://github.com/FreezeManny/labops/issues/47)) ([ed6e07c](https://github.com/FreezeManny/labops/commit/ed6e07cb687726d35030d19b7ed4c13067de3e25))
* wake support ([#49](https://github.com/FreezeManny/labops/issues/49)) ([040fad8](https://github.com/FreezeManny/labops/commit/040fad820e79528a900cc62d272202e7a509b0c7))

## [0.8.0](https://github.com/FreezeManny/labops/compare/labops-v0.7.0...labops-v0.8.0) (2026-08-07)


### Features

* custom update command ([#45](https://github.com/FreezeManny/labops/issues/45)) ([093e6f8](https://github.com/FreezeManny/labops/commit/093e6f83640b15e9935a51ec8f8d5d2137b8f757))

## [0.7.0](https://github.com/FreezeManny/labops/compare/labops-v0.6.1...labops-v0.7.0) (2026-08-05)


### Features

* caddy proxy support ([#38](https://github.com/FreezeManny/labops/issues/38)) ([81036b9](https://github.com/FreezeManny/labops/commit/81036b99d6116376a02cbcf78d1470e6b4f7490a))

## [0.6.1](https://github.com/FreezeManny/labops/compare/labops-v0.6.0...labops-v0.6.1) (2026-07-14)


### Bug Fixes

* fixed auth, and swallowed failure issues ([f6fd0a7](https://github.com/FreezeManny/labops/commit/f6fd0a7501e6f27d1b0cda1c7baddbab720ab5fd))

## [0.6.0](https://github.com/FreezeManny/labops/compare/labops-v0.5.1...labops-v0.6.0) (2026-06-27)


### Features

* add unmanaged model and model validators ([aa49240](https://github.com/FreezeManny/labops/commit/aa49240bdeb73871f9dcf29d4f50dd0613b95f6b))
* add unmanaged model and model validators ([a193df4](https://github.com/FreezeManny/labops/commit/a193df4e00c8009fd425199411b1cf17a8876275))
* skipp unmanage clients during setup run ([5148598](https://github.com/FreezeManny/labops/commit/5148598480e0c620c741fb6ab66223c5ab792d82))


### Bug Fixes

* Added unmanaged tag ([6ba9a45](https://github.com/FreezeManny/labops/commit/6ba9a45947f45761c554b3e3be29f5dcbec764bd))
* added UNMANAGED_OS Export ([b3f86e8](https://github.com/FreezeManny/labops/commit/b3f86e8eab50cf2e6b8ed93b99dbcd658b001238))

## [0.5.1](https://github.com/FreezeManny/labops/compare/labops-v0.5.0...labops-v0.5.1) (2026-05-22)


### Bug Fixes

* Typing issue ([136a43f](https://github.com/FreezeManny/labops/commit/136a43f3674024d5208f817a3aa8631344cdfac7))

## [0.5.0](https://github.com/FreezeManny/labops/compare/labops-v0.4.1...labops-v0.5.0) (2026-04-24)


### Features

* add docker-ansible ([4af4157](https://github.com/FreezeManny/labops/commit/4af415716f14fab0799cadf320b9e24ea6fb9a9b))
* added docker cli, stack finder, list function and prepared for further functions ([89b7638](https://github.com/FreezeManny/labops/commit/89b7638108b953bfbb2f6841410c23ec77c6e713))
* added docker stack duplicate name validator ([72ca51b](https://github.com/FreezeManny/labops/commit/72ca51bb303aa0dfdafabe5ce74f90b430adbd37))
* added hostname, proxyname and ip checking ([829ae15](https://github.com/FreezeManny/labops/commit/829ae15fffa69de5a3777977379f1e481a7e3c03))
* Added Unmanaged modle ([6c4717a](https://github.com/FreezeManny/labops/commit/6c4717a576c79d0391a9ae7e8044c41cf51c9e75))
* enhance docker usability ([71c4383](https://github.com/FreezeManny/labops/commit/71c438339404393e3a59fc8130e7fe7667f18a2b))
* implement Docker support for stack sync update and deploy ([7112c17](https://github.com/FreezeManny/labops/commit/7112c170b6f68d3fc40ceed5d1aab223e2d908bb))
* refactor to use state.model instead of get_model in CLI modules ([26111ed](https://github.com/FreezeManny/labops/commit/26111ede3a1e0b8ed5e2cd174a3586fa4aa45e16))


### Bug Fixes

* docker source path ([0faf604](https://github.com/FreezeManny/labops/commit/0faf604998986d0529be9c33239b93c630b23cd5))
* setup host with ssh/password mixed ([1a720fe](https://github.com/FreezeManny/labops/commit/1a720febe5e96848d234de988e071e670e219074))
* Updated Stack_name Option ([2450a07](https://github.com/FreezeManny/labops/commit/2450a07bc677b2ddb6a092b4248d170b757c8169))
* yaml_root requireing unmanaged ([dcb3b95](https://github.com/FreezeManny/labops/commit/dcb3b9511c8711c48e33968a1f2071e447ba10a5))

## [0.4.1](https://github.com/FreezeManny/labops/compare/labops-v0.4.0...labops-v0.4.1) (2026-04-22)


### Bug Fixes

* do not allow user to have custom fields in yaml ([ef6c94a](https://github.com/FreezeManny/labops/commit/ef6c94a899bff646fadab087b21aa1cd63327c8a))

## [0.4.0](https://github.com/FreezeManny/labops/compare/labops-v0.3.2...labops-v0.4.0) (2026-04-22)


### Features

* add devcontainer commands and initialize docker attribute in Host model ([0838b09](https://github.com/FreezeManny/labops/commit/0838b099ecae1f0c51ac21b469234c561fae02a2))
* add validation for duplicate web service ports in host, lxc, and vm models ([683dd75](https://github.com/FreezeManny/labops/commit/683dd7537fb2028064316f19137b243bdf4c202a))
* added duplicate VMID Validation for proxmox host and lxc ([cb6d35a](https://github.com/FreezeManny/labops/commit/cb6d35ad07cafd7843c56c42cde98380600e0e41))
* added proxy name duplication check ([c68baf6](https://github.com/FreezeManny/labops/commit/c68baf6d4bbc90ab4d217784fb324c16d3acb33e))
* changed docker and webservice structure ([10a6da9](https://github.com/FreezeManny/labops/commit/10a6da94e1d6ddf0a6ba432243ee17412ed4af76))
* Changed LXC Structure ([95b9615](https://github.com/FreezeManny/labops/commit/95b9615dc99e9747ccff7b2be2c2b8c0833c74c9))
* enhance YAML validation by adding unique IP address check ([f9ecfdf](https://github.com/FreezeManny/labops/commit/f9ecfdf390b501832ec73bed8c2e761c2ce21662))
* Improve error handling for duplicate ports, VM IDs, and IP addresses in validators ([5fb8aa4](https://github.com/FreezeManny/labops/commit/5fb8aa427e57aeb56afc1bc754a5e41fd43679ba))
* Pretty output for one error ([6a570f0](https://github.com/FreezeManny/labops/commit/6a570f02d58ce9f0d0736968e8b0f1b3ce1e3166))


### Bug Fixes

* fixed validate ([e8d229f](https://github.com/FreezeManny/labops/commit/e8d229fa831bf3611f4680ce8205658b68adbf27))

## [0.3.2](https://github.com/FreezeManny/labops/compare/labops-v0.3.1...labops-v0.3.2) (2026-04-21)


### Bug Fixes

* Added LXC to Readme ([abb1910](https://github.com/FreezeManny/labops/commit/abb1910e8d427d93125ee81c062debe906f60d43))

## [0.3.1](https://github.com/FreezeManny/labops/compare/labops-v0.3.0...labops-v0.3.1) (2026-04-21)


### Bug Fixes

* ansible directory not in built package ([33bc327](https://github.com/FreezeManny/labops/commit/33bc32740934daed8827c9d1c30a7a1d7e38b4bc))

## [0.3.0](https://github.com/FreezeManny/labops/compare/labops-v0.2.1...labops-v0.3.0) (2026-04-21)


### Features

* Added better yaml validation ([5eb983b](https://github.com/FreezeManny/labops/commit/5eb983b7cf76468b2b43447eceaeb5a482c222b5))
* Added LXC-Updater via Remote pct host connection ([a7fbf83](https://github.com/FreezeManny/labops/commit/a7fbf83885f2deb1162ed1f1a9dac6e8059d3142))


### Bug Fixes

* host source setup ([d45f5f2](https://github.com/FreezeManny/labops/commit/d45f5f2f572b1244c5f0ac2d7c131747066ee8c5))
* Removed unused ty_extension Import ([425c044](https://github.com/FreezeManny/labops/commit/425c044188d3e9597f594059c00637e117a682bc))
* typing ([9d35418](https://github.com/FreezeManny/labops/commit/9d35418088ce61e605d3cface5dc1543d3223d39))

## [0.2.1](https://github.com/FreezeManny/labops/compare/labops-v0.2.0...labops-v0.2.1) (2026-04-19)


### Bug Fixes

* removed not needed import ([9d25a09](https://github.com/FreezeManny/labops/commit/9d25a0975c4aad51e1c58752c6153e1a30e6bf6a))
* removed not needed import ([198ecb8](https://github.com/FreezeManny/labops/commit/198ecb8154c1d723adc3abfb663448199403b3a0))

## [0.2.0](https://github.com/FreezeManny/labops/compare/labops-v0.1.6...labops-v0.2.0) (2026-04-19)


### Features

* added vm setup (same as host) ([f58a908](https://github.com/FreezeManny/labops/commit/f58a908d3bd50437fcc1395276742ba67c21fa40))
* CLI Refactor to have single, shared model loader ([5890d00](https://github.com/FreezeManny/labops/commit/5890d001ffe1514fd63fe17bfef86d8932d92fa2))


### Bug Fixes

* modified VM Table ([414749d](https://github.com/FreezeManny/labops/commit/414749d62d8831b64dd60b6fdd2029eac5aa23da))

## [0.1.6](https://github.com/FreezeManny/labops/compare/labops-v0.1.5...labops-v0.1.6) (2026-04-19)


### Bug Fixes

* Renamed CLI from lops to labops ([128d98c](https://github.com/FreezeManny/labops/commit/128d98c35350b5a2e3dffe5dda5acbf69e7caf6e))

## [0.1.5](https://github.com/FreezeManny/labops/compare/labops-v0.1.4...labops-v0.1.5) (2026-04-19)


### Documentation

* added readme ([0de3501](https://github.com/FreezeManny/labops/commit/0de35013d0ca357201a8f93e3416d9cb772d412b))

## [0.1.4](https://github.com/FreezeManny/labops/compare/labops-v0.1.3...labops-v0.1.4) (2026-04-19)


### Bug Fixes

* updated cli-text ([5dfeefc](https://github.com/FreezeManny/labops/commit/5dfeefcdf0b3e31bafde56408a090798a423db48))

## [0.1.3](https://github.com/FreezeManny/labops/compare/labops-v0.1.2...labops-v0.1.3) (2026-04-19)


### Bug Fixes

* added more typing ([560d5e9](https://github.com/FreezeManny/labops/commit/560d5e96fcb98d0fc4d7ef6b40e7a99a46478efc))

## [0.1.2](https://github.com/FreezeManny/labops/compare/labops-v0.1.1...labops-v0.1.2) (2026-04-19)


### Bug Fixes

* update uv.lock ([5140fab](https://github.com/FreezeManny/labops/commit/5140fab45bee0f1dfafcf39ec2b05a49c099efc3))

## [0.1.1](https://github.com/FreezeManny/labops/compare/labops-v0.1.0...labops-v0.1.1) (2026-04-19)


### Bug Fixes

* changed name ([8e252ee](https://github.com/FreezeManny/labops/commit/8e252eefdcfd9613dd88f0491f7eb3582aff0a0e))
* changed name ([58a8bfc](https://github.com/FreezeManny/labops/commit/58a8bfcc7f7d2e556dd1335543fc8893aae3589a))
