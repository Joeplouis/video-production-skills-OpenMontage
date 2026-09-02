module.exports = {
  apps: [
    {
      name: "vpms",
      cwd: "/opt/empire/apps/VIDEO-PRODUCT-MANAGEMENT-SYSTEM/repo",
      script: "/usr/bin/python3",
      args: "-m uvicorn vpms.main:app --host 0.0.0.0 --port 8093",
      env: {
        DATABASE_URL: "postgresql://empire:empire_pass_2026@localhost:5435/affiliates_autopilot"
      },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      time: true
    }
  ]
}
