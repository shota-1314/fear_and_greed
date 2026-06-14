# VPS Operations

## バッチ実行

テスト実行:

```bash
python main.py --test
```

件数指定実行:

```bash
python main.py --limit 10
```

本番実行:

```bash
ENV=production python main.py
```

## 高速化用の環境変数

```env
REQUEST_SLEEP_SECONDS="1"
DAILY_MARGIN_SCRAPE_PAGES="1"
INITIAL_MARGIN_SCRAPE_PAGES="2"
```

- `REQUEST_SLEEP_SECONDS`: 銘柄間の待機秒数です。
- `DAILY_MARGIN_SCRAPE_PAGES`: 既に信用倍率データがある銘柄で、日次実行時に取得する株探ページ数です。
- `INITIAL_MARGIN_SCRAPE_PAGES`: 初回などDBに信用倍率データがない銘柄で取得する株探ページ数です。

## cron確認

GitHub Actionsのデプロイ時に `scripts/install_cron.sh` が実行され、平日17時のcronが登録されます。

確認:

```bash
crontab -l
```

想定されるcron:

```cron
0 17 * * 1-5 cd /var/www/fear_and_greed_new && ENV=production /var/www/fear_and_greed_new/venv/bin/python main.py >> /var/www/fear_and_greed_new/output.log 2>&1 # fear_and_greed_new weekday batch
```
