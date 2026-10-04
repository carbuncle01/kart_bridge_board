# kart_bridge_board Rev.2 — KiCadプロジェクト

| 項目 | 値 |
| --- | --- |
| Board ID | `JPBB-01` |
| Revision | `Rev.2` |
| 外形 | 60 × 30 mm |
| PCB | 4層、1.0 mm |
| 積層 | JLCPCB標準4層（指定なし） |
| 表面処理 | Lead-free HASL |
| PCBA面 | Top side |
| 主電源 | J5 pin 2からのTBLE-04SR BEC |
| USB VBUS | D2/U3経由でMCU／3.3 Vロジックを給電。VBEC、MUX、サーボ、ESCから分離 |
| 既定信号経路 | MANUAL |

Rev.1はGitタグ`JPBB-01-Rev.1`で復元できます。Rev.2の価格差と発注値はリポジトリ直下の`docs/rev2_cost_optimization.md`を参照してください。

## Rev.2固有の注意

- 配線・書き込み操作の余裕を確保するため外形は60 × 30 mm。H1/H2はなく、B面中央の20 × 12 mm平坦領域へ両面テープで固定する。
- 4層・1.0 mmと連続In1 GNDを維持し、JLCPCB標準積層、標準FR-4 TG135、Lead-free HASLを選ぶ。インピーダンス管理は指定しない。
- 全ビア穴径は0.30 mm以上。
- 抵抗とセラミックコンデンサは0402（1005 metric）。C1だけは`EEHZK1E101UP`（100 µF / 25 V、LCSC `C454668`）の導電性高分子ハイブリッドアルミ電解SMD。
- U1は`STM32G0B1CBT6`（LCSC `C2847904`、128 KiB）。ファームウェア容量を確認し、旧BOMと混在させない。
- U2は`TMUX7236PWR`（LCSC `C37096021`）。在庫が少ない可能性があるため、発注直前に在庫を確保する。
- C2、Y1、C12、C13、TP9〜TP12はRev.2に存在しない。
- USBクロックは外部水晶ではなくSTM32G0B1のHSI48/CRSを使う。
- J1〜J5はDNPで、PCBA後に2.54 mmヘッダーを手はんだする。
- J7はSamtec `FTSH-105-01-L-DV-007-K`（LCSC `C5296739`）をPCBA実装する。Cortex SWDの物理position 7を省いたキー付きコネクタで、VTrefは電源入力ではない。
- SW1（RST）とSW2（BOOT）はPCBA実装する。初回だけST-LINKで`BOOT_LOCK=0`、`nBOOT1=1`、`nBOOT_SEL=0`へ設定し、その後はUSB ROM DFUを使用できる。
- D1/D2はVBECとUSB VBUSを`LOGIC_RAW`へダイオードORし、U3が+3V3を生成する。USB単独時はMCUだけを起動し、VBEC系負荷へは給電しない。
- U5はVBECが有効範囲に達するまでTMUX7236の出力を無効化する。
- `USB_DIFF`の線幅0.15 mm / 間隔0.15 mmは短いUSB Full-Speed配線用の名目値で、90 Ω製造保証は付けない。

## 製造出力

```bash
./scripts/rebuild.sh
```

これは回路図、プロジェクト設定、配線済みPCBを再生成し、独立基板監査後に製造出力まで作成します。KiCadファイルを再生成せず製造出力だけを更新する場合は次を使用します。

```bash
./scripts/export.sh
```

`fabrication/build/`の最終レポートを確認してから、Gerber ZIP、BOM CSV、CPL CSVをJLCPCBの各欄へ個別にアップロードします。CLI DRCが異常終了する、レポートが生成されない、または違反が残る場合は合格扱いにせず、KiCad GUIのDRCを含む再確認が終わるまで発注しません。詳細な発注・初回通電条件はリポジトリ直下の`docs/design_review.md`を参照してください。

2026-07-23のRev.2生成時点では、KiCad 10.0.4でERC/DRC、未接続、回路図・PCB差分、独立基板監査、JLCPCB BOM/CPL整合性がすべてPASSしています。`fabrication/build/reports/build_manifest.txt`に集約結果を保存します。macOS版KiCad 10.0.4だけで必要になるCLI互換シムは`run_kicad_drc.sh`が限定適用し、DRC規則や違反は抑制しません。

## 書き込み

J7へST-LINKを接続するときは基板をUSB-CまたはBECで給電し、J7 pin 1（VTref）へST-LINKから電源を供給しません。初回オプション設定後のUSB DFUは、SW2（BOOT）を押したままSW1（RST）を押して離し、続いてSW2を離してからSTM32CubeProgrammerのUSB接続を選びます。詳細はリポジトリ直下の`docs/design_review.md`を参照してください。
