---
{"id": "fullstack:case:crypto-dashboard", "project": "crypto-dashboard", "title": "Live crypto price dashboard", "client_industry": "fintech", "category": "frontend", "date": "2023-05-03", "skills": ["WebSockets", "React", "D3.js", "TypeScript"]}
---
# Live crypto price dashboard

## The problem
Traders needed sub-second charts across 40 pairs.

## What I did
React with D3 canvas charts fed by exchange WebSockets, throttled with requestAnimationFrame.

## Result
Rendered 40 live charts at 60 FPS on a mid-range laptop.

## Stack
WebSockets, React, D3.js, TypeScript
