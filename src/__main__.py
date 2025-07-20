import os
import re

from dotenv import load_dotenv

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from pyairtable import Api

from src.thread_manager import ThreadManager

load_dotenv()

# Slack setup
app = App(token=os.getenv("SLACK_BOT_TOKEN"))
client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
user_client = WebClient(token=os.getenv("SLACK_USER_TOKEN"))

CHANNEL = os.getenv("CHANNEL_ID")

# Airtable setup
airtable_api = Api(os.getenv("AIRTABLE_API_KEY"))
airtable_base = airtable_api.base(os.getenv("AIRTABLE_BASE_ID"))

# Thread stuff
thread_manager = ThreadManager(airtable_base)


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
    if thread_manager.has_active_thread(user_id):
        thread_info = thread_manager.get_active_thread(user_id)

        try:
            response = client.chat_postMessage(
                channel=CHANNEL,
                thread_ts=thread_info["thread_ts"],
                text=f"{message_text}",
                username=user_info["display_name"],
                icon_url=user_info["avatar"]
            )
            thread_manager.update_thread_activity(user_id)
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

        success = thread_manager.create_active_thread(
            user_id,
            CHANNEL,
            response["ts"],
            response["ts"]
        )

        return success
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
    if thread_manager.has_active_thread(target_user_id):
        thread_info = thread_manager.get_active_thread(target_user_id)

        try:
            client.chat_postMessage(
                channel=CHANNEL,
                thread_ts=thread_info["thread_ts"],
                text=f"*Staff started:*\n{staff_message}"
            )
            success = send_dm_to_user(target_user_id, staff_message)
            thread_manager.update_thread_activity(target_user_id)

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
        thread_manager.create_active_thread(
            target_user_id,
            CHANNEL,
            response["ts"],
            response["ts"]
        )

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

    # DMs to the bot
    if channel_type == "im":
        handle_dms(user_id, message_text, say)
    # Replies in the support channel
    elif channel_id == CHANNEL and "thread_ts" in message:
        print(f"Processing channel reply in thread {message['thread_ts']}")
        handle_channel_reply(message, client)

def handle_channel_reply(message, client):
    """Handle replies in channel to send them to users"""
    thread_ts = message["thread_ts"]
    reply_text = message["text"]

    # Find user's active thread by TS
    target_user_id = None
    for user_id in thread_manager.active_cache:
        thread_info = thread_manager.get_active_thread(user_id)

        if thread_info and thread_info["thread_ts"] == thread_ts:
            target_user_id = user_id
            break

    if target_user_id:
        success = send_dm_to_user(target_user_id, reply_text)

        if success:
            thread_manager.update_thread_activity(target_user_id)
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

        success = thread_manager.complete_thread(user_id)
        if success:
            print(f"Marked thread for user {user_id} as completed")
        else:
            print(f"Failed to mark {user_id}'s thread as completed")

    except SlackApiError as err:
        print(f"Error marking thread as completed: {err}")

@app.action("delete_thread")
def handle_delete_thread(ack, body, client):
    """Handle deleting thread"""
    ack()

    user_id = body["actions"][0]["value"]
    message_ts = body["message"]["ts"]

    try:
        thread_info, is_active = thread_manager.delete_thread(user_id, message_ts)

        if not thread_info:
            print(f"Couldn't find thread info for {user_id} (messages ts {message_ts})")
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