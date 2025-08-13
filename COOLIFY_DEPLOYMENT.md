# Coolify Deployment Guide

## Prerequisites
1. Coolify instance running and accessible
2. Git repository pushed to GitHub/GitLab/Gitea
3. All required environment variables ready

## Deployment Steps

### 1. Create New Resource in Coolify
1. Login to your Coolify dashboard
2. Click "New Resource" → "Application"
3. Select your Git provider and repository
4. Choose "Docker" as the build pack

### 2. Configure Build Settings
- **Build Pack**: Docker
- **Dockerfile**: `Dockerfile` (default)
- **Build Context**: `.` (root directory)
- **Port**: `3000` (required by Coolify even for bots)

### 3. Set Environment Variables
Add these environment variables in Coolify:

```
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_BOT_TOKEN=xoxb-your-bot-token
CHANNEL_ID=C1234567890
SLACK_USER_TOKEN=xoxp-your-user-token
AIRTABLE_API_KEY=your-airtable-key
AIRTABLE_BASE_ID=your-base-id
```

### 4. Configure Advanced Settings
- **Restart Policy**: Unless Stopped
- **Memory Limit**: 512MB
- **CPU Limit**: 0.5 cores
- **Health Check**: Enabled (uses built-in Docker health check)

### 5. Deploy
1. Click "Deploy" to start the build process
2. Monitor the build logs
3. Once deployed, check the application logs to ensure the bot is running

## Monitoring
- Use Coolify's built-in logs viewer
- Health checks will automatically restart the bot if it fails
- The bot will automatically reconnect to Slack if connection is lost

## Troubleshooting
- Check environment variables are set correctly
- Verify Slack tokens have proper permissions
- Ensure Airtable base and tables exist
- Review application logs in Coolify dashboard

## Auto-Deploy
Set up webhooks in your Git repository to trigger automatic deployments on push to main branch.