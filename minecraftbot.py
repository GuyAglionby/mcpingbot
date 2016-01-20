from telegram import Updater
from telegram.dispatcher import run_async
import telegram
import yaml
import socket
import struct
import re
import uuid
import base64
import json
import os
import logging

log = logging.getLogger()
logging.basicConfig()
log.setLevel(logging.INFO)

PROTOCOL_VERSION = 47
# Corresponds to section symbol plus any character
colour_regex = re.compile("\xa7.")

# # # # # # #
# Encoding  #
# # # # # # #
# See https://developers.google.com/protocol-buffers/docs/encoding#varints

def decode_varint(sock):
    mask = 0x7F
    result = 0

    for i in range(5):
        income = ord(sock.recv(1))
        extracted = income & mask
        result |= extracted << i * 7
        # MSB check
        if not income & 0x80:
            break

    return result

def encode_varint(value):
    mask = 0x7F
    result = ""

    while value > 0:
        enc = value & mask
        value >>= 7
        result += struct.pack('B', (1 if value > 0 else 0) + enc)

    return result

def encode_string(string):
    return encode_varint(len(string)) + string

# # # # # # #
# Commands  #
# # # # # # #

def start_command(bot, update):
    message = "Commands:\n/ping host[:port] - Ping a minecraft server "
    bot.sendMessage(update.message.chat_id, text=message)

# Network calls are blocking so run asynchronously
@run_async
def ping_command(bot, update, **kwargs):
    chat_id = update.message.chat_id
    split_message = update.message.text.split()

    if len(split_message) == 2:
        bot.sendChatAction(chat_id=chat_id, action=telegram.ChatAction.TYPING)
        data = ping_server(split_message[1])

        if 'Error' in data:
            bot.sendMessage(chat_id, text=data, disable_web_page_preview=True)
        else:
            max_players = data['players']['max']
            players = data['players']['online']
            description = strip_colour(data['description'])

            if 'favicon' in data:
                file_name = uuid.uuid4().hex + '.png'
                file_out = open(file_name, 'w')
                favicon_data = data['favicon'].replace('data:image/png;base64,', '')
                file_out.write(base64.b64decode(favicon_data))
                file_out.close()
                # Photo captions are ASCII only and are limited to width of the photo
                # As such, send the sever info in a separate message
                bot.sendPhoto(chat_id, photo=open(file_name, 'rb'))
                os.remove(file_name)

            message = u'{0}:\n{1}/{2} players online\n\n{3}'.format(split_message[1], players, max_players, description)
            bot.sendMessage(chat_id, text=message, disable_web_page_preview=True)
    else:
        bot.sendMessage(chat_id, text="Incorrect syntax: /ping <server>")


# # # # # # # # #
# MC Networking #
# # # # # # # # #
# http://wiki.vg/Server_List_Ping
def ping_server(socket_string):
    # Extract host and port from socket (or use default port if none given)
    host = socket_string
    port = 25565
    socket_split = socket_string.split(":")

    if len(socket_split) > 2:
        return {"Error": "Error: Invalid socket {0}".format(socket_string)}

    if len(socket_split) == 2:
        try:
            host = socket_split[0]
            port = int(socket_split[1])
        except ValueError:
            return {"Error": "Error: Invalid port {0}".format(socket_split[1])}

    # Ping the server
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect((host, port))
    except socket.gaierror:
        return {"Error": "Error: Invalid hostname {0}".format(host)}
    except socket.error:
        return {"Error": "Error: Connection timed out"}

    # Sending handshake & request
    sock.send(encode_string("\x00" + encode_varint(PROTOCOL_VERSION) + encode_string(host.encode('utf-8')) + struct.pack('>H', port) + "\x01"))
    sock.send(encode_string("\x00"))

    # Receiving response
    decode_varint(sock)
    decode_varint(sock)
    length = decode_varint(sock)

    data = ""
    while len(data) < length:
        data += sock.recv(1024)
    sock.close()
    return json.loads(data.decode('utf8'))

# # # # # # #
# Utilities #
# # # # # # #
def strip_colour(string):
    return colour_regex.sub("", string)

def main():
    settings = file('minecraftsettings.yml', 'r')
    yaml_data = yaml.load(settings)
    token = yaml_data['telegram-apikey']
    updater = Updater(token)
    disp = updater.dispatcher
    updater.start_polling()

    # Register commands
    disp.addTelegramCommandHandler('ping', ping_command)
    disp.addTelegramCommandHandler('start', start_command)

    # CLI
    while True:
        try:
            text = raw_input()
        except NameError:
            text = input()

        if text == 'stop':
            updater.stop()
            break

if __name__ == '__main__':
    main()
