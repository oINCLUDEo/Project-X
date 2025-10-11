# Operational Runbook

## Bot Commands

### Admin Commands

#### `/info` - Post and Cluster Debugging
**Usage:**
- `/info <post_id>` - Show detailed information about a specific post
- Reply to bot message with `/info` - Show cluster information for generated news

**What it shows:**
- Post metadata: channel ID, cluster ID, engagement score, channel reputation
- Ad classification history and decisions
- Cluster statistics: total views, reactions, comments, forwards
- Average metrics per post in cluster
- Sample of first 5 posts in cluster

**Use cases:**
- Debugging why a post wasn't clustered properly
- Checking ad classification accuracy
- Monitoring cluster quality and engagement
- Investigating user feedback issues

#### `/label` - Manual Ad Classification
**Usage:** `/label <post_id> <ad|not_ad|ambiguous> [notes]`

**Purpose:** Manually label posts for training the ad classifier

**Examples:**
- `/label 12345 ad` - Mark post as advertisement
- `/label 12345 not_ad` - Mark post as not advertisement  
- `/label 12345 ambiguous "borderline case"` - Mark as ambiguous with notes

#### `/start` - User Registration
**Usage:** `/start`

**Purpose:** Register new users in the system

## System Monitoring

### Key Metrics to Monitor
- Cluster creation rate
- Ad classification accuracy
- User engagement with generated news
- Telegram API rate limits
- Database connection health

### Common Issues and Solutions

#### Bot Not Responding
1. Check logs in `logs/tgnews.log`
2. Verify Telegram bot token is valid
3. Check database connectivity
4. Restart bot process

#### Low Cluster Quality
1. Use `/info` to analyze problematic clusters
2. Check clustering parameters in config
3. Review news source quality
4. Adjust similarity thresholds

#### Ad Classification Issues
1. Use `/label` to manually correct misclassified posts
2. Retrain classifier with new labels
3. Review classification thresholds
4. Check for new ad patterns

## Configuration

### Key Settings
- `local_tz_offset_minutes`: Timezone offset for date matching
- `generated_lookup_prefix_len`: Length of text prefix for cluster matching
- Clustering parameters: similarity thresholds, minimum cluster size
- Ad classification thresholds

### Environment Variables
- `TELEGRAM_BOT_TOKEN`: Bot authentication token
- `DATABASE_URL`: Database connection string
- `AI_API_KEY`: AI service API key

## Logs

### Log Files
- `logs/tgnews.log`: Main application logs
- `logs/logs_exmp.log`: Example log format

### Log Levels
- `DEBUG`: Detailed debugging information
- `INFO`: General application flow
- `WARNING`: Potential issues
- `ERROR`: Error conditions
- `CRITICAL`: Critical failures

## Database Maintenance

### Regular Tasks
- Clean up expired clusters
- Archive old posts
- Update channel reputation scores
- Backup user data

### Schema Changes
- Always backup before schema changes
- Test changes on development environment
- Document changes in CHANGELOG.md
- Update this runbook if commands change

