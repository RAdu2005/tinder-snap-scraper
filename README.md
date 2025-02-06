# Tinder API Snap Scraper
Scrape Snapchat usernames from Tinder using HTTP API calls and OpenAI for filtering bio's. This app requires you to have working (can be shadowbanned) Tinder accounts with their X-Auth-Token, refresh-token, persistent-device-id and an individual HTTPS proxy for each account. 

Additionally provides a tool to update the X-Auth-Token for the accounts that also requires a key for ImageTyperz API for solving FunCaptcha if prompted. Includes .proto file and its .py compilation for auth gateway. Repo includes their Python captcha client, rights are their own.

## Setup
Install dependenices
`pip install -r requirements.txt`

Create inputs.csv file with the following columns on top row:
`X-Auth-Token,refresh-token,persistent-device-id,proxy`
populate with accounts according to description.

Run `python scraper.py` once to generate a .env file and fill with your OpenAI key (must have gpt-4o-mini access) and optionally ImageTyperz key if you intend to use the auth token refresher.

## Use

### Scraper
To run the scraper use 
`python scraper.py`
this uses multithreading pools so the more threads your CPU has the faster it will run.

This will create a `bios` folder which contains scraped bio's from accounts it encounters.

After exhausting the daily limit (around 800-1000 people) you can run
`python filter.py`
which will display a list of the Snapchat usernames found. Optionally you can redirect to file with `>`.

#### Note 1: Some accounts proxies may be bad, the app will notify you about them, change their proxy if you want to use them!
#### Note 2: I recommend deleting all the files in `/bios` after every run, otherwise you will get a lot of duplicate usernames.

### Refresher
To run the refresher use:
`python refresh_token.py`
This will refresh input.csv with new X-Auth-Token values.

Accounts that get a SELFIE_CHALLENGE or that can't solve their captcha in one try get eliminated from the list. Additionally, accounts with bad proxies will get put into a separate .csv file to check.

# I don't take any responsability for any actions against ToS performed with this bot!