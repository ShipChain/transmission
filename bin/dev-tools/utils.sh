#!/bin/bash

# Not everyone uses the same color variables :-(
export COLOR_NC='\e[0m' # No Color
export COLOR_WHITE='\e[1;37m'
export COLOR_BLACK='\e[0;30m'
export COLOR_BLUE='\e[0;34m'
export COLOR_LIGHT_BLUE='\e[1;34m'
export COLOR_GREEN='\e[0;32m'
export COLOR_LIGHT_GREEN='\e[1;32m'
export COLOR_CYAN='\e[0;36m'
export COLOR_LIGHT_CYAN='\e[1;36m'
export COLOR_RED='\e[0;31m'
export COLOR_LIGHT_RED='\e[1;31m'
export COLOR_PURPLE='\e[0;35m'
export COLOR_LIGHT_PURPLE='\e[1;35m'
export COLOR_BROWN='\e[0;33m'
export COLOR_YELLOW='\e[1;33m'
export COLOR_GRAY='\e[0;30m'
export COLOR_LIGHT_GRAY='\e[0;37m'

function color_header() {
    if [[ -z "$2" ]] ; then C="$COLOR_CYAN"; else C="$2"; fi
    echo
    echo -e "$C----------------------"
    echo "$1"
    echo -e "----------------------$COLOR_NC"
}

function git_status {
  DIRTY=0
  UNTRACKED=0
  ADDED=0
  OUT=$(git status 2> /dev/null)
  [[ "$( echo $OUT | grep 'Changes not staged for commit:')" != "" ]] && DIRTY=1
  [[ "$( echo $OUT | grep 'Untracked files:')" != "" ]] && UNTRACKED=1
  [[ "$( echo $OUT | grep 'Changes to be committed:')" != "" ]] && ADDED=1
  if [[ ADDED -ne 0 || DIRTY -ne 0 || UNTRACKED -ne 0 ]]; then
      echo "DIRTY"
  else
      echo "CLEAN"
  fi
}

function slack_text {
    PAYLOAD="payload={\"text\": \"$*\"}"
    URL="https://hooks.slack.com/services/**/**"
    curl -X POST $URL --data-urlencode "$PAYLOAD"
}

function ec2json() {
 aws ec2 describe-instances | jq -r '.Reservations[].Instances[] | {type: .InstanceType, state: .State.Name, ip: .PublicIpAddress, name: (.Tags[] | select(.Key == "Name") | .Value), id: .InstanceId}'
}

function ec2info() {
 ec2json | jq -r 'reduce . as $i (""; . + "["+$i.type + "|"+$i.state+"]\t"+$i.name[:15]+"\t"+ $i.id +"\t"+ $i.ip)' | sort
}
