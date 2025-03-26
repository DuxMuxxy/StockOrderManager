### Setup

```bash
python3 -m venv venv
venv/bin/activate
pip install flask flask_sqlalchemy discord.py gunicorn sqlalchemy psycopg2_binary python-dotenv
```

### Front

> python main.py


### Bot Discord

#### Setup token

New .env file at the project root :

```
DISCORD_BOT_TOKEN={token_here}
```

> python discord_bot.py

