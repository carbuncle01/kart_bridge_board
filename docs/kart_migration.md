# Kart Bridge Board移行記録

作成日: 2026-10-04

## 出自と範囲

- 元: `/Users/at/project/tmp/jetpilot_bridge_board`
- 元コミット: `7f6d7d9826f38714a328d490e095e2bd3a551ea3`
- 新: `/Users/at/project/tmp/kart_bridge_board`
- 元の追跡ファイル90個をコピーし、独立したGit履歴を開始。旧リモート・履歴・タグは継承しない。
- CMakeプロジェクト名: `kart_bridge_firmware`。段階選択: `KART_STEP`。
- KiCadのプロジェクト・ファイル名・参照パス・基板名称を`kart_bridge_board`へ変更。
- USB製造者／製品／インターフェース表示をKartへ変更。VID/PID `0483:5740`とシリアル生成方式は維持。
- Board ID `JPBB-01`、Rev.2、C識別子`jpbb_*`/`JPBB_*`、通信フレーム`JPB1`は互換性のため維持。
- 制御、プロトコル、全8段階のmain.c、ピン定義、リンカは元ファイルとバイト一致。C/ヘッダー/リンカの差分はUSB表示文字列のみ。
- 図版は既存Rev.2の参考資料を継承。KiCad名称変更後のERC/DRC・レンダリング・製造出力は今回未検証。
- Kart側ROS 2 bridgeは本リポジトリの範囲外。旧環境固有の起動コマンドを新環境の実装済み機能として記載しない。

## 再現手順

リポジトリルートで実行する。

```bash
./firmware/scripts/test.sh
./firmware/scripts/build.sh all
```

最終版だけなら`./firmware/scripts/build.sh step8_final`。
生成先は`firmware/build/<step>/<step>.elf`、`.hex`、`.bin`。
依存ライブラリとツールは`firmware/vendor/`へ配置しGit管理外とする。
別PCでの取得手順は`firmware/README.md`を参照。

## 確認済み

- `firmware/scripts/test.sh`: 制御ロジック・通信プロトコルの既存ホスト単体テストPASS。
- 静的検査: 8段階の配置、回路図とのピン一致、初期段階のMANUAL固定、128 KiB Flash上限PASS。

## ARMビルド結果（2026-10-04）

- 全8段階のReleaseビルド成功。ELF/HEX/BIN計24ファイルの存在・非空を確認。
- Arm GNU Toolchain 13.2.Rel1（GCC 13.2.1、macOS arm64）、CMake 4.4.4、Ninja 1.13.2。
- STM32CubeG0 v1.6.3: `878a6fd8ad440c70ee32bc6d7ad526babb6e04f4`。
- Step 8: Flash 29,292 bytes / 128 KiB、RAM 6,688 bytes / 144 KiB（リンカ出力）。
- ローカル詳細ログ: `firmware/build/build-all.log`（Git管理外）。
- 警告あり: 元コードのUSB長マクロ再定義、ST CMSIS/USB内の整数変換、nosysの未実装syscall。今回の名称移行ではこれらの実装変更は行っていない。
- 実機の動作確認は含まない。

| Step | BIN bytes | BIN SHA-256 |
| --- | ---: | --- |
| `step1_safe_boot` | 13956 | `7474962f1f043cfa1b5d1b0d4421c4787418efa22e08862195c8f3ba32ba9f1d` |
| `step2_usb_cdc` | 17980 | `cd2ac5f5de6a69f0e22a3c3d2e6fdfd12ff7b5ded34871a317cb130c92485b28` |
| `step3_rc_input` | 19480 | `f2aa90071ab15b00811b4808f2b0cd944c8b8f5f6c549d4d8d73a1b8058721ee` |
| `step4_pwm_output` | 22396 | `a2d99399998248e0c509876edb43a1da6c18854db860025f193e74180d3550e7` |
| `step5_manual_auto` | 23976 | `92e9d87d740ce668f34895b42b407d743ad329a603482c85c177101f1ec9bb78` |
| `step6_failsafe` | 27096 | `f4c0069e57a8cfe90edc51c322be617ca93b0e86f60117df4b4a63edb3f0c9f2` |
| `step7_full_bridge` | 28064 | `1a19442143224598e55ada643b5156993cb3e6f27c8a2d4dc98c638296afc3e3` |
| `step8_final` | 29292 | `9d7486f2c66e7172300aeee89cf4bca2a949390ba81ed645ad3bbb401e087c5b` |

## 未検証

実機への書き込み、USB列挙、実サーボ/ESC動作、実機フェイルセーフ、Kart本体との接続。
USB製品名を含むLinuxの`/dev/serial/by-id/`パスは変更されるため、接続先を再確認する。

## 依存ソフトの一次資料

- [Arm GNU Toolchain](https://developer.arm.com/Tools%20and%20Software/GNU%20Toolchain)
- [STM32CubeG0 v1.6.3](https://github.com/STMicroelectronics/STM32CubeG0/tree/v1.6.3)
