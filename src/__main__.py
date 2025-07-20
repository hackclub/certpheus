import os
import re

from dotenv import load_dotenv

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

app = App(token=os.getenv("SLACK_BOT_TOKEN"))
client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
user_client = WebClient(token=os.getenv("SLACK_USER_TOKEN"))

user_threads = {}
completed_threads = {}

CHANNEL = os.getenv("CHANNEL_ID")


def get_standard_channel_msg(user_id, message_text):
    """Get blocks for a standard message uploaded into channel with 2 buttons"""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"(User ID: `{user_id}`)"
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message_text
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Reply in this thread to send a response to the user"
                }
            ]
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Mark as Completed"
                    },
                    "style": "primary",
                    "action_id": "mark_completed",
                    "value": user_id
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Delete thread"
                    },
                    "style": "danger",
                    "action_id": "delete_thread",
                    "value": user_id,
                    "confirm": {
                        "title": {
                            "type": "plain_text",
                            "text": "Are you sure?"
                        },
                        "text": {
                            "type": "mrkdwn",
                            "text": "This will delete the entire thread and new replies will go into a new thread"
                        },
                        "confirm": {
                            "type": "plain_text",
                            "text": "Delete"
                        },
                        "deny": {
                            "type": "plain_text",
                            "text": "Cancel"
                        }
                    }
                }
            ]
        }
    ]

def get_user_info(user_id):
    """Get user's profile info"""
    try:
        response = client.users_info(user=user_id)
        user = response["user"]
        return {
            "name": user["real_name"] or user["name"],
            "avatar": user["profile"].get("image_72", ""),
            "display_name": user["profile"].get("display_name", user["name"])
        }
    except SlackApiError as err:
        print(f"Error during user info collection: {err}")
        return None

def post_message_to_channel(user_id, message_text, user_info):
    """Post user's message to the given channel, either as new message or new reply"""
    if user_id in user_threads:
        try:
            response = client.chat_postMessage(
                channel=CHANNEL,
                thread_ts=user_threads[user_id]["thread_ts"],
                text=f"{message_text}",
                username=user_info["display_name"],
                icon_url=user_info["avatar"]
            )
            return True
        except SlackApiError as err:
            print(f"Error writing to a thread: {err}")
            return False
    else:
        return create_new_thread(user_id, message_text, user_info)

def create_new_thread(user_id, message_text, user_info):
    """Create new thread in the channel"""
    try:
        response = client.chat_postMessage(
            channel=CHANNEL,
            text=f"*{user_id}*:\n{message_text}",
            username=user_info["display_name"],
            icon_url=user_info["avatar"],
            blocks=get_standard_channel_msg(user_id, message_text)
        )

        user_threads[user_id] = {
            "thread_ts": response["ts"],
            "channel": CHANNEL,
            "message_ts": response["ts"]
        }

        if user_id not in completed_threads:
            completed_threads[user_id] = []
        return True
    except SlackApiError as err:
        print(f"Error creating new thread: {err}")
        return False

def send_dm_to_user(user_id, reply_text):
    """Send a reply back to the user"""
    try:
        dm_response = client.conversations_open(users=[user_id])
        dm_channel = dm_response["channel"]["id"]

        client.chat_postMessage(
            channel=dm_channel,
            text=reply_text,
            username="Fraudpheus",
            icon_emoji=":orph:"
        )
        print(f"Successfully sent reply to user {user_id}: {reply_text[:50]}...")
        return True
    except SlackApiError as err:
        print(f"Error sending reply to user {user_id}: {err}")
        print(f"Error response: {err.response}")
        return False

def extract_user_id(text):
    """Extracts user ID from a mention text <@U000000> or from a direct ID"""
    # 'Deep' mention
    mention_format = re.search(r"<@([A-Z0-9]+)>", text)
    if mention_format:
        return mention_format.group(1)

    # Direct UID
    id_match = re.search(r"\b(U[A-Z0-9]{8,})\b", text)
    if id_match:
        return id_match.group(1)

    return None


@app.command("/fdchat")
def handle_fdchat_cmd(ack, respond, command):
    """Handle conversations started by staff"""
    ack()

    command_text = command.get("text", "").strip()

    # Validation goes brrr
    if not command_text:
        respond({
            "response_type": "ephemeral",
            "text": "Usage: /fdchat @user your message' or '/fdchat U000000 your message'"
        })
        return

    # Getting the info about request
    parts = command_text.split(" ", 1)
    user_id = parts[0]
    staff_message = parts[1]
    print(command_text)
    print(user_id)
    print(staff_message)

    # Enter the nickname pls
    target_user_id = extract_user_id(user_id)
    if not target_user_id:
        respond({
            "response_type": "ephemeral",
            "text": "Provide a valid user ID: U000000 or a mention: @name"
        })
        return

    # Get user info
    user_info = get_user_info(target_user_id)
    if not user_info:
        respond({
            "response_type": "ephemeral",
            "text": f"Couldn't find user info for {target_user_id}"
        })
        return

    # Check if user has an active thread, if so - use it
    if target_user_id in user_threads:
        try:
            client.chat_postMessage(
                channel=CHANNEL,
                thread_ts=user_threads[target_user_id]["thread_ts"],
                text=f"*Staff started:*\n{staff_message}"
            )
            success = send_dm_to_user(target_user_id, staff_message)

            if success:
                respond({
                    "response_type": "ephemeral",
                    "text": f"Message sent in some older thread to {user_info['display_name']}"
                })
            else:
                respond({
                    "response_type": "ephemeral",
                    "text": f"It sucks, couldn't add a message to older thread for {user_info['display_name']}"
                })
            return
        except SlackApiError as err:
            respond({
                "response_type": "ephemeral",
                "text": f"Something broke, awesome - couldn't add a message to an existing thread"
            })
            return
    # Trying to create a new thread
    try:
        success = send_dm_to_user(target_user_id, staff_message)
        if not success:
            respond({
                "response_type": "ephemeral",
                "text": f"Failed to send DM to {target_user_id}"
            })
            return

        response = client.chat_postMessage(
            channel=CHANNEL,
            text=f"*Staff started:* {staff_message}",
            username=user_info["display_name"],
            icon_url=user_info["avatar"],
            blocks=get_standard_channel_msg(target_user_id, staff_message)
        )

        # Track the thread
        user_threads[target_user_id] = {
            "thread_ts": response["ts"],
            "channel": CHANNEL,
            "message_ts": response["ts"]
        }

        if target_user_id not in completed_threads:
            completed_threads[target_user_id] = []

        respond({
            "response_type": "ephemeral",
            "text": f"Started conversation with {user_info['display_name']}, good luck"
        })

        print(f"Successfully started conversation with {target_user_id} via slash command")

    except SlackApiError as err:
        respond({
            "response_type": "ephemeral",
            "text": f"Error starting conversation: {err}"
        })

def handle_staff_start(message, say):
    """Handle conversations started by staff"""
    channel_id = message.get("channel")
    message_text = message["text"]
    request_user_id = message["user"]

    # Fancy guard against unauthorized usage
    if channel_id != CHANNEL:
        return False
    if not (message_text.startswith("/fdchat ") or message_text.startswith("!fdchat ")):
        return False

    content = message_text[7:]
    parts = content.split(" ")
    if len(parts) < 2:
        say("Usage: '/fdchat @user your message' or '/fdchat U000000 your message'")
        return True

    user_id = parts[1]
    staff_message = ' '.join(parts[2:])

    target_user_id = extract_user_id(user_id)
    if not target_user_id:
        print(target_user_id)
        say("Provide a valid user ID (U000000) or a mention (@user)")
        return True

    user_info = get_user_info(target_user_id)
    if not user_info:
        say(f"Couldn't find user info for {target_user_id}")
        return True

    if target_user_id in user_threads:
        say(f"User {user_info['display_name']} has an active thread")
        try:
            client.chat_postMessage(
                channel=CHANNEL,
                thread_ts=user_threads[target_user_id]["thread_ts"],
                text=f"*Staff started:*\n{staff_message}"
            )
            send_dm_to_user(target_user_id, staff_message)
            return True
        except SlackApiError as err:
            say(f"Error adding message to an existing thread: {err}")
            return True

    try:
        success = send_dm_to_user(target_user_id, staff_message)
        if not success:
            say(f"Failed to send DM to user {target_user_id}")
            return True

        response = client.chat_postMessage(
            channel=CHANNEL,
            text=f"*Staff started:* {staff_message}",
            username=user_info["display_name"],
            icon_url=user_info["avatar"],
            blocks=get_standard_channel_msg(target_user_id, staff_message)
        )

        user_threads[target_user_id] = {
            "thread_ts": response["ts"],
            "channel": CHANNEL,
            "message_ts": response["ts"]
        }

        if target_user_id not in completed_threads:
            completed_threads[target_user_id] = []

        try:
            client.chat_delete(
                channel=CHANNEL,
                ts=message["ts"]
            )
        except SlackApiError:
            pass

        print(f"Successfully started conversation with {target_user_id}")
        return True
    except SlackApiError as err:
        say(f"Couldn't start message with {target_user_id}: {err}")
        return True

def handle_dms(user_id, message_text, say):
    """Receive and react to messages sent to the bot"""
    user_info = get_user_info(user_id)
    if not user_info:
        say("Hiya! Couldn't process your message, try again another time")
        return
    success = post_message_to_channel(user_id, message_text, user_info)
    if not success:
        say("There was some error during processing of your message, try again another time")

@app.message("")
def handle_all_messages(message, say, client, logger):
    """Handle all messages related to the bot"""
    user_id = message["user"]
    message_text = message["text"]
    channel_type = message.get("channel_type", '')
    channel_id = message.get("channel")

    #print(f"Message received - Channel: {channel_id}, Type: {channel_type}")

    if channel_type == "im":
        handle_dms(user_id, message_text, say)
    elif channel_id == CHANNEL and "thread_ts" in message:
        print(f"Processing channel reply in thread {message['thread_ts']}")
        handle_channel_reply(message, client)

def handle_channel_reply(message, client):
    """Handle replies in channel to send them to users"""
    thread_ts = message["thread_ts"]
    reply_text = message["text"]

    print(f"Processing reply in thread {thread_ts}: {reply_text}")

    target_user_id = None
    for user_id, thread_info in user_threads.items():
        if thread_info["thread_ts"] == thread_ts:
            target_user_id = user_id
            break

    print(f"Found target user: {target_user_id}")

    if target_user_id:
        success = send_dm_to_user(target_user_id, reply_text)

        if success:
            print(f"Successfully sent reply to user {target_user_id}")
        else:
            print(f"Failed to send reply to user {target_user_id}")
            try:
                client.reactions_add(
                    channel=CHANNEL,
                    timestamp=message["ts"],
                    name="x"
                )
            except SlackApiError as err:
                print(f"Failed to add X reaction: {err}")
    else:
        print(f"Could not find user for thread {thread_ts}")


@app.action("mark_completed")
def handle_mark_completed(ack, body, client):
    """Complete the thread"""
    ack()

    user_id = body["actions"][0]["value"]
    messages_ts = body["message"]["ts"]

    try:
        client.reactions_add(
            channel=CHANNEL,
            timestamp=messages_ts,
            name="white_check_mark"
        )

        if user_id in user_threads:
            completed_threads[user_id].append(user_threads[user_id].copy())

        del user_threads[user_id]
        print(f"Marked thread for user {user_id} as completed")
    except SlackApiError as err:
        print(f"Error marking thread as completed: {err}")

@app.action("delete_thread")
def handle_delete_thread(ack, body, client):
    """Handle deleting thread"""
    ack()

    user_id = body["actions"][0]["value"]
    message_ts = body["message"]["ts"]

    try:
        thread_info = None
        is_active = False
        thread_index = -1

        if user_id in user_threads and user_threads[user_id]["message_ts"] == message_ts:
            thread_info = user_threads[user_id]
            is_active = True
        else:
            if user_id in completed_threads:
                for i, completed_thread in enumerate(completed_threads[user_id]):
                    if completed_thread["message_ts"] == message_ts:
                        thread_info = completed_thread
                        thread_index = i
                        break
        if not thread_info:
            print(f"Could not find thread info for user {user_id} and message {message_ts}")
            return

        thread_ts = thread_info["thread_ts"]

        try:
            response = client.conversations_replies(
                channel=CHANNEL,
                ts=thread_ts,
                inclusive=True
            )
            messages = response["messages"]
            print(f"{len(messages)} messages to delete")

            for message in messages:
                try:
                    user_client.chat_delete(
                        channel=CHANNEL,
                        ts=message["ts"],
                        as_user=True
                    )
                except SlackApiError as err:
                    try:
                        client.chat_delete(
                            channel=CHANNEL,
                            ts=message["ts"]
                        )
                    except SlackApiError as err:
                        print(f"Couldn't delete messages {message['ts']}: {err}")
                        continue
        except SlackApiError as err:
            print(f"Error deleting thread: {err}")

        if is_active:
            del user_threads[user_id]
        elif thread_index >= 0:
            completed_threads[user_id].pop(thread_index)
        print(f"Deleted thread for user {user_id}")
    except SlackApiError as err:
        print(f"Error deleting thread: {err}")

@app.event("message")
def handle_message_events(body, logger):
    """Please just don't spam errors that I have unhandled request"""
    pass

@app.error
def error_handler(error, body, logger):
    logger.exception(f"Error: {error}")
    logger.info(f"Request body: {body}")

if __name__ == "__main__":
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    print("Bot running!")
    handler.start()