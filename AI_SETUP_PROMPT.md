# AI Assistant Setup Prompt for AlphaEdge

*Copy and paste the prompt below to any AI assistant (like ChatGPT, Claude, or Gemini) to have it guide you step-by-step through installing and configuring the AlphaEdge Trading Bot on a new machine.*

---

**PROMPT:**

"You are an expert Python algorithmic trading engineer. I have a repository containing the **AlphaEdge Trading Bot** (a MetaTrader 5 institutional-grade trading bot). I need you to guide me step-by-step through installing, configuring, and running this bot on my Windows machine. 

Please walk me through the following steps in order, waiting for my confirmation after each step before moving on to the next:

**Step 1: Python & Environment Setup**
Guide me on how to check if Python is installed, how to clone the repository, and how to create and activate a Python virtual environment (`venv`). 

**Step 2: Install Dependencies**
Provide the command to install the necessary libraries (`MetaTrader5`, `pandas`, `python-dotenv`, `schedule`, etc.) assuming there is a standard `requirements.txt` or just listing the core libraries if not.

**Step 3: MetaTrader 5 Configuration**
Explain how to ensure MT5 is installed, logged into my broker account, and critically, how to enable 'Allow Algorithmic Trading' in the MT5 options.

**Step 4: Environment Variables (.env) Injection**
Provide a template for a `.env` file that the bot needs. Explain exactly how to create this file in the root directory and fill it with:
- `MT5_LOGIN` (My account number)
- `MT5_PASSWORD` (My account password)
- `MT5_SERVER` (My broker's server name, exactly as it appears in MT5)
- `TELEGRAM_TOKEN` (My Telegram bot token from BotFather)
- `TELEGRAM_CHAT_ID` (My Telegram Chat ID)

**Step 5: Launching the Bot**
Give me the final command to run `python start_bot.py`. Tell me what success logs I should expect to see in the terminal to confirm the Autonomous Scanner and Telegram Bot have started successfully.

Please start by giving me the instructions for Step 1."
