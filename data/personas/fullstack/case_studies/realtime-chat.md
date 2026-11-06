---
{"id": "fullstack:case:realtime-chat", "project": "realtime-chat", "title": "Real-time classroom chat", "client_industry": "edtech", "category": "frontend", "date": "2021-07-23", "skills": ["WebSockets", "Node.js", "Redis", "React", "Socket.IO"]}
---
# Real-time classroom chat

## The problem
Teachers lost students in long video calls with no side channel.

## What I did
Socket.IO chat with Redis pub/sub so it scales across instances, plus moderation tools.

## Result
Handled 8,000 concurrent users at peak with p95 message latency of 120 ms.

## Stack
WebSockets, Node.js, Redis, React, Socket.IO
