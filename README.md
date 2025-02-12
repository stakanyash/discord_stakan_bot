# "stakanyasher" Discord server bot

**Simple bot for my Discord server**

---
## Commands:

### Admin Commands:

- `!mute @username duration reason` - Mutes a user for a specified duration
- `!unmute @username` - Unmutes a user
- `!warn @username reason` - Issues a warning to a user. If a user receives 3 warnings within the last 24 hours, they are muted for 24 hours
- `!warnremove @username` - Removes all warnings from a user
- `!warnings @username` - Displays a list of warnings for a user
- `!mute_all` - Mutes all channel members for 1 hour (used for `!bomb` command)
- `!subscribe` - Allows users to subscribe to a role to receive notifications about new YouTube videos
- `!subscribesecond` - Allows users to subscribe to a role to receive notifications about new videos on a second YouTube channel
- `!getvideosid` - Checks the latest videos on specified YouTube channels and updates their IDs in the database
- `!check_youtube_channels` - Checks YouTube channels for new videos and sends notifications to a specified channel

### Commands Available to Everyone:

- `!MrCarsen` - Sends a random message from a list of quotes
- `!золотойфонд` - Sends a random message from the "золотой фонд" (gold fund)
- `!неумничай` - Sends the message "Да пошёл ты нахуй!"
- `!аможетбытьты` - Sends the message "КТО?! Я?!"
- `!ахуйтебе` - Sends the message "Сукпыздыц((9(((("
- `!пошёлтынахуй` - Sends the message "Та за що, плять?.."
- `!рулетка` - Simulates "Russian roulette." If a "shot" occurs, the user is muted for 1 minute
- `!bomb` - Initiates a "bomb" in the chat. Chat participants must defuse it within an hour, or everyone will be muted for 1 hour
- `!defuse 1234` - Defuses the initiated "bomb" (where `1234` is your code attempt)
- `!help` or `!помощь` - Sends a message with a list of available commands and their descriptions
- `!ХУЯБЛЯ` - Sends the message "БАН!" and mutes the user for 1 minute
