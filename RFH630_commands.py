# ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# This file contains the sopas comments that correspond to the RHF 630
# ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

from __future__ import division
import math

# Inventory / Get UID (All in field)
get_UID = '\x02sMN CSGtUID\x03'

# Start transmission
start_tx = "\x02"

# End transmission
end_tx = "\x03"

# Empty space
empty_space = "\x00"

# Read multiple blocks as string
read_multiple_string = "\x02sMN RdMltBlckStr\x03"

# Write multiple blocks as string
write_multiple_string = "sMN WrtMltBlckStr"

write_multiple_test = '\x02sMN WrtMltBlckStr 20 E1 75 37 50 1 4 E0 0 1 8 12345679\x03'


def write_custom_string(tag_uid, user_entry):
    """
This functions takes the raw input from the user and completes the SOPAS command from SICK
in order to transmit the information to the RFID transponder
    """

    # initialize the padding string
    padding_string = ""

    # Calculate the number of blocks, each block holds up to 4 characters
    block_count = int(math.ceil(len(user_entry) / 4))

    # the start and finish blocks in the memory of the tag
    start_block = str(0)
    finish_block = str(block_count - 1)

    # check if padding at the end is necessary
    padding_amount = 4 - len(user_entry) % 4
    if padding_amount != 4:

        # add so many empty spaces as needed
        for i in range(0, padding_amount):
            padding_string += empty_space

        normalized_length = len(user_entry) + padding_amount
        string_count_hex = format(normalized_length, '02X')

        if string_count_hex[0] == "0":
            string_count_hex = string_count_hex[1]

        transmission_command = start_tx + write_multiple_string + " " + tag_uid + " " + start_block + " " + finish_block \
                               + " " + string_count_hex + " " + user_entry + padding_string + end_tx
    # if fraction part is 0, characters are multiple of 4
    else:

        string_count_hex = format(len(user_entry), '02X')

        if string_count_hex[0] == "0":
            string_count_hex = string_count_hex[1]

        transmission_command = start_tx + write_multiple_string + " " + tag_uid + " " + start_block + " " + finish_block \
                               + " " + string_count_hex + " " + user_entry + end_tx

    return transmission_command


def read_tag_content(tag_uid):
    """
    This functions takes takes the UID of a previously detected tag and creates the command to send to the 
    RFID transponder
    """

    # Invert the order of the UID
    list_length = len(tag_uid)

    # Initialize the lists
    list_uid = []
    reversed_list = []

    # Generate a list from the UID string
    for character in range(0, list_length):
        list_uid.append(tag_uid[character])

    forward_counter = 0

    # Invert the list and save it in a different one
    for inverse_counter in range(list_length-1, 0, -1):
        reversed_list.append(list_uid[inverse_counter])
        forward_counter += 1

    print reversed_list

    # Start and finish block can in this case be hard coded, the data structure to write and read is immutable
    start_block = "0"
    finish_block = "5"

    read_multiple_command = start_tx + read_multiple_string + " " + tag_uid + " " + start_block + " " + finish_block + \
                            end_tx

    return read_multiple_command

