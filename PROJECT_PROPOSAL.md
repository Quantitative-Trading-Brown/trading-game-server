# Project Proposal: Real-Time Trading Game Server

## Overview

A multiplayer real-time trading simulator where players compete in a simulated financial market. Players join game lobbies, place orders on securities, and manage risk under margin constraints. Automated market-maker bots provide liquidity, and an admin controls the game lifecycle. The server handles order matching, position tracking, margin enforcement, and real-time broadcasting of market data to all connected clients.

## Problem Statement

Teaching trading concepts like order books, margin, liquidation, and market making is difficult in a classroom or workshop setting. Existing paper-trading platforms are either too complex for beginners or lack the competitive, time-boxed format that drives engagement. This project provides a controlled, gamified environment where participants learn by doing -- placing real orders against each other and bots in a live market.

## Core Features

### Game Lifecycle
- Lobby creation: Admin creates a game, receives a 6-digit join code
- Player join: Players authenticate and join via code
- Configurable presets: Games are defined by JSON configs specifying securities, tick count, tick duration, margins, bot behavior, and historical price data (CSV)
- Tick-based clock: Game advances in discrete ticks (e.g., 1500 ticks x 2s = 50 min)
- State machine: SETUP -> LIVE -> SETTLEMENT -> RESULTS

### Trading Engine
- Order types: Limit orders and market orders
- Price-time priority matching: Standard exchange-style order book per security
- Atomic execution: All order/trade operations are locked to prevent race conditions
- Cancel support: Cancel individual orders or all open orders

### Risk Management
- Margin requirements: Configurable long/short margin per security
- Margin calls: Warning period (N ticks) before forced liquidation
- Liquidation: Auto-close all positions at market price
- Bankruptcy: Cash reset with limited retries; elimination after max bankruptcies

### Market-Maker Bots
- Simple MM: Places bids/asks around a target price from CSV data with configurable spread width
- Skewed MM: Adds random skew for asymmetric liquidity
- Bot manager: Executes bot cycles every N ticks, cancels stale orders before placing new ones

### Real-Time Communication
- WebSocket (SocketIO): Bidirectional real-time updates
- Per-tick broadcasts: Order book changes, price updates, news
- On-demand snapshots: Full game state for late joiners or reconnects
- Separate namespaces: `/player` and `/admin` with different visibility

### Scoring
- Final score = cash + liquidation-adjusted position value at true prices
- Leaderboard generation and ranking
