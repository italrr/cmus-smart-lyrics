#!/usr/bin/env python3

import requests
import json
import curses
import time
import sys
import os
import hashlib
import threading
from subprocess import PIPE, Popen

def gprint(msg):
	command = "notify-send \""+msg+"\""
	Popen(command, stdout=PIPE, stderr=None, shell=True)

def get_tag(input, tagname):
	lines = input.splitlines()
	for line in lines:
		tokens = line.split(" ")
		if tokens[1] == tagname:
			v = ' '.join(tokens[2:])
			return v
	return None

def get_filename(input):
	lines = input.splitlines()
	for line in lines:
		tokens = line.split(" ")
		if tokens[0] == "file":
			v = os.path.basename(' '.join(tokens[1:])).rsplit( ".", 1 )[ 0 ]
			return v	
	return None

def get_current_song():
	song = {"artist": "", "title": "", "md5": ""}
	command = "cmus-remote -Q 2>/dev/null"
	with Popen(command, stdout=PIPE, stderr=None, shell=True) as process:
		output = process.communicate()[0].decode("utf-8")
		#(output)
		t_title = get_tag(output, "title")
		t_artist = get_tag(output, "artist")
		filename = get_filename(output)
		song["title"] = filename if t_title ==  None else t_title
		song["artist"] = "" if t_artist == None else t_artist
		song["md5"] = hashlib.md5((song["title"] + "-" + song["artist"]).encode('utf-8')).hexdigest() 
	return song

def is_player_running():
	command = "cmus-remote -Q 2>/dev/null"
	with Popen(command, stdout=PIPE, stderr=None, shell=True) as process:
		output = process.communicate()[0].decode("utf-8")
		return output != ""
	return False

def fetch_from_mip(song):
	url = "https://makeitpersonal.co/lyrics?artist=%s&title=%s" % (song["artist"], song["title"])
	resp = requests.get(url)
	if resp.status_code != 200:
		return { "success": False, "reason": "failed to connect to makeitpersonal.co" }
	if "We don't have lyrics for this song yet" in resp.text:
		return { "success": False, "reason": resp.text }
	return { "success": True, "type": "plain", "lyrics": resp.text.splitlines() }

def fetch_from_ovh(song):
	url = "https://api.lyrics.ovh/v1/%s/%s" % (song["artist"], song["title"])
	resp = requests.get(url)
	if resp.status_code == 404:
		return { "success": False, "reason": "song not found" }		
	if resp.status_code != 200:
		return { "success": False, "reason": "failed to connect to ovh: code %i" % str(resp.status_code) }
	jobj = json.loads(resp.text)
	return { "success": True, "type": "plain", "lyrics": jobj["lyrics"].splitlines() }	


def fetch_from_all(song):
	all = []

	lyrics = fetch_from_mip(song)
	if lyrics != None and lyrics["success"]:
		all.append(lyrics)

	lyrics = fetch_from_ovh(song)	
	if lyrics != None and lyrics["success"]:
		all.append(lyrics)

	return all

stdscr = None
win_width = 0
win_height = 0
last_song = None
is_running = False
stdscr = curses.initscr()
win_height, win_width = stdscr.getmaxyx()
is_running = True
current_lyrics = None
ui_title = ""
ui_body = []
ui_bottom = "";
ui_body_cursor_y = 0

curses.start_color()
curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
curses.use_default_colors()
curses.init_pair(2, -1, -1)

def window_clear():
	stdscr.clear()
	stdscr.refresh()

def window_draw_text(str, x, y, color):
	if len(str) >= win_width:
		str = str[0:win_width-1]
	stdscr.addstr(y, x, str, color)
	stdscr.refresh()	
	
def redraw_ui():
	global ui_body_cursor_y
	global ui_body
	stdscr.clear()
	# title
	for w in range(0, win_width):
		stdscr.insch(0, w, " ", curses.color_pair(1))
	window_draw_text(ui_title, 0, 0, curses.color_pair(1))
	# body
	for i in range(0, win_height-2):
		chunk = "\n"
		if i + ui_body_cursor_y < len(ui_body) and len(ui_body) > 0:
			chunk = ui_body[i + ui_body_cursor_y]
		window_draw_text(chunk, 0, 1 + int(i), curses.color_pair(2))
	# bottom
	for w in range(0, win_width):
		stdscr.insch(win_height-1, w, " ", curses.color_pair(1))
	window_draw_text(ui_bottom, 0, win_height-1, curses.color_pair(1))
	
	stdscr.refresh()

def update_ui(title, body, bottom):
	global ui_title
	global ui_bottom
	global ui_body
	ui_title = title
	ui_bottom = bottom
	if body != None:
		ui_body = body
	redraw_ui()	

def core_thread():
	global ui_title
	global ui_bottom
	global ui_body
	global is_running
	global last_song
	while is_running:
		try:
			time.sleep(1)
			if not is_player_running():
				ui_title = "CMUS is not running."
				ui_bottom = ""
				redraw_ui()
				continue
			current = get_current_song()
			#gprint(str(current))
			if last_song != None and current["md5"] == last_song["md5"]:
				#gprint("skipped")
				last_song = current
				continue
			last_song = current
			update_ui("Fetching lyrics for %s" % current["title"], [], "")
			found = fetch_from_all(current)
			if len(found) == 0:
				update_ui("No lyrics found for %s" % current["title"], [], "")
				continue
			update_ui(current["title"] + " by " + current["artist"], found[0]["lyrics"], "PRESS [UP] OR [DOWN] TO SCROLL")
		except Exception as ex:
			with open('xD.txt', 'a') as f:
				f.write(str(ex))
				f.close()
			sys.exit(1)
			
core_thread_handle = threading.Thread(target=core_thread, args=())
core_thread_handle.start()

redraw_ui()

while is_running:
	key = stdscr.getch()
	if key == 65:
		ui_body_cursor_y -= 1
		if ui_body_cursor_y < 0:
			ui_body_cursor_y = 0 
	elif key == 66:
		ui_body_cursor_y += 1
		if ui_body_cursor_y >= len(ui_body):
			ui_body_cursor_y = len(ui_body)-1
			
	resize = curses.is_term_resized(win_height, win_width)
	if resize:
		win_height, win_width = stdscr.getmaxyx()
		curses.resizeterm(win_height, win_width)
    	
	redraw_ui()

core_thread_handle.join()

curses.endwin()
