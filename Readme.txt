

                 YOUR UBUNTU MACHINE
                 /home/ahmed/rag_resume
                           |
              +------------+------------+
              |                         |
              v                         v
       DEVELOPMENT                 PRODUCTION
       Port: 8502                  Port: 8501
              |                         |
       Bind Mount                    Docker Image
       ./ -> /app                       |
              |                         |
              v                         v
       rag-resume-app-dev         rag-resume-app
              |                         |
              v                         v
       ahmed-postgres-dev        ahmed-postgres
       Port: 5434                Port: 5433
              |                         |
              v                         v
       resumedb_dev              resumedb



       1. Development
   |
   v
2. Write Code Locally
   |
   v
3. Docker Development Container
   |
   v
4. Run Tests
   |
   v
5. Git Commit + Push
   |
   v
6. GitHub Actions
   |
   v
7. Tests + Security + Docker Build
   |
   v
8. Merge Approved Changes
   |
   v
9. Production Deployment