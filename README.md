# Plex24
#

A telegram bot to temporarily or permanently share our libraries on Plex

The program is functional but still in an early stage, undergoing constant modifications.

## Usage

User command

1. /plex24 - Invite and share libraries for 24 hours.
   
Admin commands

1. /plexdel - remove pending invite.
2. /plexkick - remove friend.
3. /plexmese - Create an account with one month expiration.
4. /plexfull - Create an account with no expiration or convert Plex24 to PlexFull.
5. /ping - Verify if the VPS is online 

## Dependencies

- pip install -r requirements.txt

## Installation

1. Clone this repository.
2. Install the required dependencies using PIP.
3. Run the script with awbot.py

## Configuration ( .env file)

session_name=plex24h
api_id=your telegram data
api_key=your telegram data
bot_token=your telegram bot data
adminId= telegram adimin user id
interroga= update time in seconds
serverIp= plex server IP
serverToken=plex token


## Contribution

Contributions are welcome! Feel free to open an issue or submit a pull request.
