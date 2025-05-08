# Delphi Enrichment

Delphi is a profile enrichment tool that helps verify and enhance user profiles using social media data.

## Project Structure

```
delphi/
├── frontend/          # Next.js frontend application
└── backend/           # FastAPI backend application
```

## Prerequisites

- Python 3.8+ (for backend)
- Node.js 16+ (for frontend)
- npm or yarn (for frontend)

## Setup

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create and activate a virtual environment (optional but recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

## Running the Application

### Backend

From the `backend` directory:
```bash
uvicorn app:app --reload
```
The backend server will start at `http://localhost:8000`

### Frontend

From the `frontend` directory:
```bash
npm run dev
```
The frontend development server will start at `http://localhost:3000`

## Features

- Profile search and enrichment
- Social media profile verification
- Manual profile confirmation
- Dark mode support
- High contrast text for accessibility

## Development

- The frontend is built with Next.js and uses Tailwind CSS for styling
- The backend is built with FastAPI
- The application supports both light and dark modes
- High contrast text is implemented for better accessibility

## API Endpoints

The backend provides the following main endpoints:

- `/api/enrich` - Enriches profile data
- `/api/confirm_profile` - Confirms profile information
- `/api/full_profile` - Retrieves full profile data

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request 