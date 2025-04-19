#!/usr/bin/env bash

API_URL="http://localhost:8000/chat/stream"
SESSION_FILE="/tmp/chat_session_id"
VERSION="1.1"

# Colors
RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
PURPLE='\033[1;35m'
CYAN='\033[1;36m'
NC='\033[0m' # No Color

# Function to print messages with colors
print_msg() {
    local color="$1"
    shift
    echo -e "${color}$*${NC}"
}

# Initialize or load session
if [ -f "$SESSION_FILE" ]; then
    SESSION_ID=$(cat "$SESSION_FILE")
    print_msg "${CYAN}" "Resuming session: ${SESSION_ID:0:8}..."
else
    SESSION_ID=""
    print_msg "${YELLOW}" "Starting new conversation (type 'exit' or Ctrl+C to end)"
fi

# Header
clear
print_msg "${PURPLE}" "=== Chat API Tester v${VERSION} ==="
echo -e "Endpoint: ${BLUE}${API_URL}${NC}"
[ -n "$SESSION_ID" ] && echo -e "Session:  ${CYAN}${SESSION_ID:0:8}...${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

cleanup() {
    echo
    print_msg "${YELLOW}" "Conversation ended. Session saved for next time."
    exit 0
}
trap cleanup SIGINT

while true; do
    echo -en "\n${GREEN}You: ${NC}"
    read -r USER_MESSAGE
    
    # Check for exit commands
    [[ "$USER_MESSAGE" =~ ^(exit|quit|bye)$ ]] && break
    [ -z "$USER_MESSAGE" ] && continue

    # URL encode the message
    ENCODED_MESSAGE=$(jq -rn --arg msg "$USER_MESSAGE" '$msg | @uri')
    PARAMS="message=$ENCODED_MESSAGE"
    [ -n "$SESSION_ID" ] && PARAMS+="&session_id=$SESSION_ID"

    # Stream the response with better formatting
    print_msg "${BLUE}" "Bot: "
    RESPONSE_BUFFER=""
    FIRST_CHUNK=true
    
    curl -sN "$API_URL?$PARAMS" | while IFS= read -r line; do
        case "$line" in
            "data: [DONE]"*)  # Ignore the DONE marker
                ;;
            data:*)
                CONTENT="${line#data: }"
                CONTENT="${CONTENT%$'\n'}"  # Trim trailing newline
                
                # For first chunk, ensure we don't add extra space
                if [ "$FIRST_CHUNK" = true ]; then
                    printf "%s" "$CONTENT"
                    FIRST_CHUNK=false
                else
                    printf " %s" "$CONTENT"
                fi
                
                RESPONSE_BUFFER+="$CONTENT"
                ;;
            event:end*)
                echo  # Newline after stream ends
                ;;
            event:error*)
                echo -e "\n${RED}[ERROR] Stream failed${NC}" >&2
                break
                ;;
        esac
    done

    # Store new session ID if created
    if [ -z "$SESSION_ID" ] && [ -n "$RESPONSE_BUFFER" ]; then
        SESSION_ID=$(curl -s -X POST "http://localhost:8000/chat" \
            -H "Content-Type: application/json" \
            -d "{\"message\":\"$USER_MESSAGE\"}" | jq -r '.session_id')
        echo "$SESSION_ID" > "$SESSION_FILE"
        print_msg "${PURPLE}" "New session started: ${SESSION_ID:0:8}..."
    fi
done

cleanup