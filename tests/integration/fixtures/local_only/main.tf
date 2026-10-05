terraform {
  required_providers {
    time = {
      source  = "hashicorp/time"
      version = "~> 0.11"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

resource "time_sleep" "wait" {
  create_duration = "3s"
}

resource "local_file" "output" {
  depends_on = [time_sleep.wait]
  filename   = "${path.module}/output.txt"
  content    = "hello from nac integration test\n"
}
