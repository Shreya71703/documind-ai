# Portfolio Screenshot Plan

This document outlines the required screenshots for the DocuMind AI portfolio presentation.

## 1. Landing Page
- **State**: Unauthenticated root route (`/`).
- **Visible Elements**: Hero section, value proposition, "Get Started" call to action.
- **Sensitive Data**: None.

## 2. Authenticated Application Shell
- **State**: User logged in, viewing an empty `/app` workspace.
- **Visible Elements**: Left sidebar (Conversations), center empty state, right drawer trigger (Knowledge Base).
- **Sensitive Data**: None (use a demo user like `demo@example.com`).

## 3. Knowledge Base
- **State**: Right sidebar open, showing multiple documents.
- **Visible Elements**: Upload dropzone, one document "Indexing...", one document "Ready" with a chunk count, one document "Failed" with a retry button.
- **Sensitive Data**: Ensure filenames are generic (e.g., `project-aurora-specs.pdf`).

## 4. New Chat Modal
- **State**: The "New Chat" dialog is open.
- **Visible Elements**: The chat title input, the list of documents where indexed documents are selectable and non-indexed are visibly disabled.
- **Sensitive Data**: None.

## 5. Grounded AI Answer
- **State**: Inside an active chat session.
- **Visible Elements**: User message bubble, Assistant message bubble containing an answer and interactive `[SOURCE 1]` citation chips.
- **Sensitive Data**: None.

## 6. Citation Metadata Popover
- **State**: The user has clicked a citation chip.
- **Visible Elements**: The citation popover showing the filename, file type, chunk index, and page number.
- **Sensitive Data**: None.

## 7. Mobile Responsive View
- **State**: Browser width reduced to simulate mobile.
- **Visible Elements**: Top navigation bar with toggle buttons, chat interface taking up the full screen.
- **Sensitive Data**: None.
