# kart_bridge_board Rev.2（低価格版）

`kart_bridge_board`は、RC車両の受信機・サーボ・ESC間に挿入する制御基板です。通常時は受信機のCH1/CH2信号をMANUAL経路で通し、許可条件が成立したときだけSTM32生成PWMへ切り替えます。

| 項目 | Rev.2の定義 |
| --- | --- |
| 正式名称 | `kart_bridge_board` |
| Board ID | `JPBB-01` |
| Revision | `Rev.2` |
| 文書日付 | 2026-07-23 |
| KiCad | 10.0.4以降 |
| 基板外形 | 60 × 30 mm |
| 基板構成 | 4層、1.0 mm |
| 積層 | JLCPCB標準4層（指定なし） |
| 内層 | In1.Cu: 連続GND、In2.Cu: VBEC |
| 表面処理 | Lead-free HASL |
| PCBA実装面 | Top sideのみ |
| 主電源 | J5 pin 2からのTBLE-04SR BEC入力 |
| USB VBUS | D2とU3を介してMCU／3.3 Vロジックを給電。VBEC、MUX、サーボ、ESCからは分離 |
| 既定信号経路 | MANUAL |

旧プロジェクトのRev.1は旧リポジトリのGitタグ`JPBB-01-Rev.1`で管理されていました。この新規リポジトリには旧履歴・タグを含めません。低価格化の差分と注文値は[docs/rev2_cost_optimization.md](docs/rev2_cost_optimization.md)を参照してください。

## ファームウェアをビルドする

このリポジトリはKart用の独立した基板・ファームウェアプロジェクトです。
ROS 2やKart本体のソースはビルドに不要です。

```bash
cd /Users/at/project/tmp/kart_bridge_board
./firmware/scripts/build.sh step8_final
# 全8段階を検証する場合
./firmware/scripts/build.sh all
./firmware/scripts/test.sh
```

依存ソフトの取得と通常のCMakeコマンドは[firmware/README.md](firmware/README.md)を参照してください。
最終版の生成先は `firmware/build/step8_final/step8_final.{elf,hex,bin}` です。
移行範囲・互換性・今回の検証結果は[docs/kart_migration.md](docs/kart_migration.md)に記録します。

## Rev.2の実装方針

- 配線余裕と書き込み操作性を確保するため、外形は60 × 30 mmです。H1/H2は削除し、B面中央の20 × 12 mm領域へ両面テープで固定します。
- 4層・1.0 mmと連続In1 GNDは維持し、JLCPCBの標準積層、標準FR-4 TG135、Lead-free HASLを使用します。製造インピーダンス指定は行いません。
- 全ビアは0.30 mm以上の穴へ統一し、0.20 mm微細ビアによる追加料金を避けます。
- 抵抗とセラミックコンデンサは0402（1005 metric）です。電源バルクのC1だけはPanasonic `EEHZK1E101UP`（100 µF / 25 V、導電性高分子ハイブリッドアルミ電解、LCSC `C454668`）です。
- MCUは同一ピン配置の`STM32G0B1CBT6`（LCSC `C2847904`、128 KiB）です。ファームウェア容量を確認し、旧BOMと混在させないでください。
- C2の追加バルクフットプリントはありません。サーボ突入でVBEC降下が問題になる場合は、外付け対策または次リビジョンで容量・電源構成を見直します。
- USBクロックはSTM32G0B1内蔵HSI48とCRSを使います。外部HSE水晶Y1と負荷コンデンサC12/C13は実装せず、フットプリントもありません。
- 表面テストポイントはTP1〜TP8です。TP9〜TP12はRev.2にありません。
- J1〜J5はPCBA非実装（DNP）で、PCBA後に2.54 mmヘッダーを手はんだします。
- J7はPCBA実装するSamtec `FTSH-105-01-L-DV-007-K`（LCSC `C5296739`）です。Cortex 10-pin SWDの物理position 7を省いたキー付きコネクタで、VTrefは電源入力ではなくターゲット電圧の参照です。
- SW1（RST）とSW2（BOOT）もPCBA実装します。初回だけJ7からオプションバイトを設定すれば、その後はUSB-Cと2個のスイッチでROM USB DFUへ入れます。
- D1/D2でVBECとUSB VBUSを`LOGIC_RAW`へダイオードORし、U3で+3V3を生成します。USBだけでもMCUは動作しますが、VBEC、U2、サーボ、ESCには給電しません。
- U5はVBECを監視し、VBECがTMUX7236の有効範囲へ達するまでMUX出力を無効化します。

## ディレクトリ

```text
hardware/kicad/kart_bridge_board/  KiCadプロジェクトと製造スクリプト
docs/                                  設計・発注・初回通電の注意事項
firmware/                              STM32G0B1用の段階別ファームウェア
tools/                                 補助ツール用の予約領域
```

## 段階別ファームウェア

`firmware/`には、MANUAL固定の起動確認からUSB指令・フェイルセーフを含む
最終版まで、`step1_safe_boot`〜`step8_final`の8段階を収録しています。
初めて接続する場合は、基板上の位置と安全な接続順を含む
[firmware/GETTING_STARTED.md](firmware/GETTING_STARTED.md)から始めてください。
ファームウェアの構成と技術的な確認項目は
[firmware/README.md](firmware/README.md)にまとめています。

## 製造データの生成

macOSのKiCad 10を想定した例です。

```bash
cd hardware/kicad/kart_bridge_board
./scripts/rebuild.sh
```

`rebuild.sh`は回路図、プロジェクト設定、配線済みPCBをソースから再生成して独立監査を行い、続けて`export.sh`を実行します。KiCadファイルを再生成せず製造出力だけを更新する場合は`./scripts/export.sh`を使用します。`fabrication/build/`へ検証レポート、Gerber ZIP、ドリル、JLCPCB用BOM/CPLを生成します。JLCPCBへはGerber ZIP、BOM CSV、CPL CSVをそれぞれ所定欄へアップロードしてください。プロジェクト一式のアーカイブは保管・引き渡し用であり、PCBA注文欄へそのままアップロードするファイルではありません。

2026-07-23のRev.2生成時点では、KiCad 10.0.4でERC Error/Warning 0、DRC Error/Warning 0、未接続0、回路図・PCB差分0、独立基板監査PASSを確認しています。結果は`fabrication/build/reports/build_manifest.txt`へ記録されます。macOS版KiCad 10.0.4で発生するCLIの既知の異常終了には、同版だけで有効になる`run_kicad_drc.sh`の最小互換シムを使用します。このシムはDRC規則や違反を抑制しません。

KiCad CLIのDRCが正常終了したかは、実行時の終了コードと生成された最終レポートで判断してください。レポートがない、CLIが異常終了する、または違反が残る場合は合格扱いにせず、KiCad GUIのDRCを含む再確認が終わるまで発注しません。

## JLCPCBへ発注する前の必須確認

この60 × 30 mm版は、以前の50 × 25 mm版とGerber、BOM、CPLのすべてが異なります。JLCPCBへ以前のデータをアップロード済みの場合は、新規注文または製造開始前の編集で3ファイルを同じビルドのものへ全て差し替えてください。旧Gerberと新BOM/CPLを混在させてはいけません。

1. `export.sh`を発注対象の最終KiCadファイルに対して実行し、ERC、DRC、未接続、回路図・PCB整合性の各チェックが正常終了し、最終レポートに違反が残っていないことを確認する。CLI DRCが異常終了した場合はGUI DRCを実行し、原因と結果を記録する。
2. JLCPCBでは「4層・1.0 mm、標準FR-4 TG135、Lead-free HASL、積層指定なし、インピーダンス指定なし、最小ビア穴0.30 mm」を選ぶ。
3. BOMのLCSC在庫と価格を注文時点で再照合する。U1は`STM32G0B1CBT6` / `C2847904`であることを確認する。特にU2の`TMUX7236PWR` / `C37096021`は在庫が少ない可能性があるため、発注直前の確保または事前購入を検討する。
4. 代替部品を選ぶ場合は、LCSC番号だけでなく、メーカー型番、ピン配置、パッケージ、動作電圧、定格を確認する。自動代替を無条件で承認しない。
5. JLCPCB部品照合画面でUSB-C、MCU、TMUX、USB ESD、LDO、U5、D1/D2、Q1〜Q4、C1、J7、SW1/SW2の実装面、pin 1、回転、極性を確認する。
6. PCBA面をTop sideにし、J1〜J5だけがDNPであること、J7とSW1/SW2は実装対象に含まれることを確認する。
7. 60 × 30 mm外形、USB-Cの張り出し、固定穴が存在しないこと、B面20 × 12 mmテープ領域、工程辺／パネル条件をオンラインGerber Viewerと注文画面で確認する。
8. BEC 1.5 Aは受信機・サーボ・基板を含む系全体の上限です。使用サーボの突入電流とストール電流を実機で確認する。
9. Rev.2にはVBEC入力の逆接保護、ヒューズ／電子過電流保護、車載サージ用TVSがありません。極性と電源条件を治具で確認し、必要な保護は上流側へ設ける。

フェイルセーフの保証範囲と初回通電はRev.1から共通の[docs/design_review.md](docs/design_review.md)、Rev.2の差分は[docs/rev2_cost_optimization.md](docs/rev2_cost_optimization.md)を参照してください。

## 初回書き込みと以後のUSB更新

初回ST-LINK設定からUSB DFU、USB CDC、Step 8の通常運用までの全体像は、
[docs/setup_flow.md](docs/setup_flow.md)を参照してください。

最初の1回はST-LINKとJ7を使います。基板はUSB-CまたはBECから給電し、ST-LINK側からJ7 pin 1へ電源を供給しないでください。STM32CubeProgrammerで接続し、`BOOT_LOCK = 0`、`nBOOT1 = 1`、`nBOOT_SEL = 0`へ設定します。`nBOOT_SEL`が正しい名称であり、`nBOOT0_SEL`ではありません。

以後はMacへUSB-Cで接続し、SW2（BOOT）を押したままSW1（RST）を押して離し、その後SW2を離すとROM USB DFUへ入れます。STM32CubeProgrammerのUSB接続からファームウェアを書き込めます。通常起動時はBOOTを押さず、RSTだけを押します。オプションバイト変更後も復旧用J7は残るため、USB更新に失敗した場合はST-LINKを再接続できます。
