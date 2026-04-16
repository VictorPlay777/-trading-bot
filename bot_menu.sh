#!/bin/bash
# Trading Bot Menu - Simple interface for bot management

cd /home/svy1990/-trading-bot

while true; do
    clear
    echo "======================================"
    echo "       Trading Bot Management"
    echo "======================================"
    echo ""
    echo "1. Start bot"
    echo "2. Stop bot"
    echo "3. Restart bot"
    echo "4. Check status"
    echo "5. View logs (live)"
    echo "6. Pull latest changes from GitHub"
    echo "7. Exit"
    echo ""
    echo "======================================"
    read -p "Select option: " choice

    case $choice in
        1)
            echo "Starting bot..."
            sudo systemctl start trading-bot
            echo "Bot started!"
            sleep 2
            ;;
        2)
            echo "Stopping bot..."
            sudo systemctl stop trading-bot
            echo "Bot stopped!"
            sleep 2
            ;;
        3)
            echo "Restarting bot..."
            sudo systemctl restart trading-bot
            echo "Bot restarted!"
            sleep 2
            ;;
        4)
            echo "Bot status:"
            sudo systemctl status trading-bot
            echo ""
            read -p "Press Enter to continue..."
            ;;
        5)
            echo "Viewing logs (Ctrl+C to exit)..."
            tail -f /home/svy1990/-trading-bot/bot.log
            ;;
        6)
            echo "Pulling latest changes..."
            git pull origin main
            echo "Changes pulled!"
            sudo systemctl restart trading-bot
            echo "Bot restarted with new changes!"
            sleep 2
            ;;
        7)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo "Invalid option!"
            sleep 1
            ;;
    esac
done
