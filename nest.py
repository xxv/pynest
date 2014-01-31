#! /usr/bin/python

# nest.py -- a python interface to the Nest Thermostat
# by Scott M Baker, smbaker@gmail.com, http://www.smbaker.com/
#
# Usage:
#    'nest.py help' will tell you what to do and how to do it
#
# Licensing:
#    This is distributed unider the Creative Commons 3.0 Non-commecrial,
#    Attribution, Share-Alike license. You can use the code for noncommercial
#    purposes. You may NOT sell it. If you do use it, then you must make an
#    attribution to me (i.e. Include my name and thank me for the hours I spent
#    on this)
#
# Acknowledgements:
#    Chris Burris's Siri Nest Proxy was very helpful to learn the nest's
#       authentication and some bits of the protocol.

import time
import urllib
import urllib2
import os
import sys
import re
import getpass
from optparse import OptionParser

try:
    import json
except ImportError:
   try:
       import simplejson as json
   except ImportError:
       print "No json library available. I recommend installing either python-json"
       print "or simplejson. Python 2.6+ contains json library already."
       sys.exit(-1)

class Nest:
    def __init__(self, username, password, serial=None, index=0, units="F", debug=False):
        self.username = username
        self.password = password
        self.serial = serial
        self.units = units
        self.index = index
        self.debug = debug
        self.headers={"user-agent":"Nest/1.1.0.10 CFNetwork/548.0.4",
                      "X-nl-protocol-version": "1"}

    def loads(self, res):
        if hasattr(json, "loads"):
            res = json.loads(res)
        else:
            res = json.read(res)
        return res

    # context ['shared','structure','device']
    def handle_put(self, context, data):
        assert context is not None, "Context must be set to ['shared','structure','device']"
        assert data is not None, "Data is None"

        new_url = self.transport_url + "/v2/put/" + context + "."

        if (context == "shared" or context == "device"):
            new_url += self.serial
        elif (context == "structure"):
            new_url += self.structure_id
        else:
            raise ValueError, context+ " is unsupported"

        req = urllib2.Request(new_url, data, self.headers)

        try:
            urllib2.urlopen(req).read()
        except urllib2.URLError:
            print "Put operation failed"
            if (self.debug):
                print new_url
                print data

    def shared_put(self, data):
        self.handle_put("shared", data)

    def device_put(self, data):
        self.handle_put("device", data)

    def structure_put(self, data):
        self.handle_put("structure", data)

    def restore_login(self):
        session = False
        try:
            data = open(os.path.expanduser('~/.config/nest/.session'))
            res = json.load(data)
            data.close()
            session = True
        except IOError:
            self.login()

        if (session):
            self.transport_url = res["urls"]["transport_url"]
            self.userid = res["userid"]
            self.headers["Authorization"] = "Basic " + res["access_token"]
            self.headers["X-nl-user-id"]= self.userid

            req = urllib2.Request(self.transport_url + "/v2/mobile/user." + self.userid,
                                  headers=self.headers)

            try:
                response = urllib2.urlopen(req)
                return True
            except urllib2.URLError as e:
                if hasattr(e, 'reason'):
                    print 'We failed to reach a server.'
                    print 'Reason: ', e.reason
                elif hasattr(e, 'code'):
                    print 'The server couldn\'t fulfill the request.'
                    print 'Error code: ', e.code

    def login(self):
        if (not self.username):
            self.username = raw_input("username: ")
        if (not self.password):
            self.password = getpass.getpass("password: ")
        data = urllib.urlencode({"username": self.username, "password": self.password})

        req = urllib2.Request("https://home.nest.com/user/login",
                              data, self.headers)

        try:
            response = urllib2.urlopen(req)
        except urllib2.URLError as e:
            if hasattr(e, 'reason'):
                print 'We failed to reach a server.'
                print 'Reason: ', e.reason
            elif hasattr(e, 'code'):
                print 'The server couldn\'t fulfill the request.'
                print 'Error code: ', e.code
            self.login()

        res = urllib2.urlopen(req).read()

        res = self.loads(res)

        with open(os.path.expanduser('~/.config/nest/.session'), 'w') as outfile:
            json.dump(res, outfile)

        self.transport_url = res["urls"]["transport_url"]
        self.userid = res["userid"]
        self.headers["Authorization"] = "Basic " + res["access_token"]
        self.headers["X-nl-user-id"]= self.userid

    def get_status(self):
        req = urllib2.Request(self.transport_url + "/v2/mobile/user." + self.userid,
                              headers=self.headers)

        res = urllib2.urlopen(req).read()

        res = self.loads(res)

        self.structure_id = res["structure"].keys()[0]
        self.structure = res["structure"][self.structure_id]["name"]

        if (self.serial is None):
            self.device_id = res["structure"][self.structure_id]["devices"][self.index]
            self.serial = self.device_id.split(".")[1]
            self.name = res["shared"][self.serial]["name"]

        self.status = res

    def temp_in(self, temp):
        if (self.units == "F"):
            return (temp - 32.0) / 1.8
        else:
            return temp

    def temp_out(self, temp):
        if (self.units == "F"):
            return temp*1.8 + 32.0
        else:
            return temp

    def show_status(self):
        shared = self.status["shared"][self.serial]
        device = self.status["device"][self.serial]
        structure = self.status["structure"][self.structure_id]

        # Delete the structure name so that we preserve the device name
        del structure["name"]
        allvars = shared

        allvars.update(structure)
        allvars.update(device)

        for k, v in sorted(allvars.items()):
            print k + "."*(32-len(k)) + ":", self.format_value(k, v)

    def format_value(self, key, value):
        if 'temp' in key and isinstance(value, float) and self.units == 'F':
            return '%s (%s F)' % (value, self.temp_out(value))

        elif 'timestamp' in key or key == 'creation_time':
            if value > 0xffffffff:
                value /= 1000
            return time.ctime(value) 

        elif key == 'mac_address' and len(value) == 12:
            return ':'.join(value[i:i+2] for i in xrange(0, 12, 2))

        else:
            return str(value)

    def show_curtemp(self):
        temp = self.status["shared"][self.serial]["current_temperature"]
        temp = self.temp_out(temp)

        temp = "%0.1f" % temp
        print self.name + " is currently " + str(temp) + u"\u00b0"

    def show_curtarget(self):
        temp = self.status["shared"][self.serial]["target_temperature"]
        temp = self.temp_out(temp)

        temp = "%0.1f" % temp
        print self.name + " is set to " + str(temp) + u"\u00b0"

    def set_temperature(self, temp):
        temp = self.temp_in(temp)
        data = '{"target_change_pending":true,"target_temperature":' + '%0.1f' % temp + '}'
        self.shared_put(data)

    def set_fan(self, state):
        data = '{"fan_mode":"' + str(state) + '"}'
        self.device_put(data)

    def set_mode(self, state):
        data = '{"target_temperature_type":"' + str(state) + '"}'
        self.shared_put(data)

    def set_away(self, state):
        time_since_epoch   = time.time()
        if (state == "away"):
            data = '{"away_timestamp":' + str(time_since_epoch) + ',"away":true,"away_setter":0}'
        else:
            data = '{"away_timestamp":' + str(time_since_epoch) + ',"away":false,"away_setter":0}'

        self.structure_put(data)

    def set_auto_away(self, state):
        if (state == "on"):
            data = '{"auto_away_enable":true}'
        else:
            data = '{"auto_away_enable":false}'
        self.device_put(data)

def create_parser():
   parser = OptionParser(usage="nest [options] command [command_options] [command_args]",
        description="Commands: fan temp mode away auto-away",
        version="unknown")

   parser.add_option("-u", "--user", dest="user",
                     help="username for nest.com", metavar="USER", default=None)

   parser.add_option("-p", "--password", dest="password",
                     help="password for nest.com", metavar="PASSWORD", default=None)

   parser.add_option("-c", "--farenheit", dest="farenheit", action="store_true", default=False,
                     help="use farenheit instead of celsius")

   parser.add_option("-s", "--serial", dest="serial", default=None,
                     help="optional, specify serial number of nest thermostat to talk to")

   parser.add_option("-d", "--debug", dest="debug", action="store_true", default=False,
                     help="Print debug information")

   parser.add_option("-i", "--index", dest="index", default=0, type="int",
                     help="optional, specify index number of nest to talk to")

   return parser

def help():
    print "syntax: nest [options] command [command_args]"
    print "options:"
    print "   --farenheit                ... use farenheit (the default is celsius)"
    print "   --serial <number>          ... optional, specify serial number of nest to use"
    print "   --index <number>           ... optional, 0-based index of nest"
    print "                                    (use --serial or --index, but not both)"
    print
    print "commands: temp, fan, away, mode, show, curtemp, humidity"
    print "    <temperature>             ... set target temperature"
    print "    fan [auto|on]             ... set fan state"
    print "    away                      ... set away state to away"
    print "    home                      ... set away state to home"
    print "    current                   ... show current temperature"
    print "    state                     ... show away state"
    print "    leaf                      ... show leaf state"
    print "    auto-away [enable|disable]... enable or disable auto away"
    print "    mode [heat|cool|range]    ... set thermostat mode"
    print "    show                      ... show everything"
    print "    humidity                  ... show current humidity"
    print
    print "examples:"
    print "    nest 73"
    print "    nest current"

def validate_temp(temp):
        try: 
            new_temp = float(temp)
        except ValueError:
            return -1
        if new_temp < 15 or new_temp > 35:
            return -1
        return new_temp
            
def main():
    parser = create_parser()
    (opts, args) = parser.parse_args()

    if(len(args)) and (args[0]=="help"):
        help()
        sys.exit(-1)

    if opts.farenheit:
        units = "F"
    else:
        units = "C"

    n = Nest(opts.user, opts.password, opts.serial, opts.index, units=units, debug=opts.debug)
    if (n.restore_login() != True):
        if ((not opts.user) or (not opts.password)):
            n.login()
    n.get_status()

    if (len(args)==0):
        n.show_curtarget()
        sys.exit(-1)

    cmd = args[0]

    if (cmd.isdigit()):
        new_temp = -1
        new_temp = validate_temp(cmd)
        if new_temp == -1:
            print "please specify a temperature between 15 and 35"
            sys.exit(-1)
        n.set_temperature(new_temp)
        print n.name + " is set to " + str(new_temp) + u"\u00b0"
    elif (cmd == "current"):
        n.show_curtemp()
    elif (cmd == "fan"):
        if len(args)<2 or args[1] not in {"on", "auto"}:
            print "please specify a fan state of 'on' or 'auto'"
            sys.exit(-1)
        n.set_fan(args[1])
    elif (cmd == "mode"):
        if len(args)<2 or args[1] not in {"cool", "heat", "range"}:
            print "please specify a thermostat mode of 'cool', 'heat'  or 'range'"
            sys.exit(-1)
        n.set_mode(args[1])
    elif (cmd == "show"):
        n.show_status()
    elif (cmd == "until"):
        if n.status["device"][n.serial]["time_to_target"] != 0:
            until = time.strftime('%I:%M%p', time.localtime(n.status["device"][n.serial]["time_to_target"])).lstrip('0')
            print n.name + " will reach it's target temperature at " + str(until).lower()
        else:
            print n.name + " has reached it's target temperature"
    elif (cmd == "humidity"):
        print "The relative humidity is currently " + str(n.status["device"][n.serial]["current_humidity"]) + "%"
    elif (cmd == "leaf"):
        if (n.status["device"][n.serial]["leaf"]):
            print n.name + " leaf is on"
        else:
            print n.name + " leaf is off"
    elif (cmd == "state"):
        if (n.status["structure"][n.structure_id]["away"]):
            print n.structure + " is set to away"
        else:
            print n.structure + " is set to home"
    elif (cmd == "away"):
        n.set_away("away")
    elif (cmd == "home"):
        n.set_away("here")
    elif (cmd == "auto-away"):
        if len(args)<2 or args[1] not in {"on", "off"}:
            print "please specify a state of 'on' or 'off'"
            sys.exit(-1)
        n.set_auto_away(args[1])
    else:
        n.show_curtemp()

if __name__=="__main__":
   main()
