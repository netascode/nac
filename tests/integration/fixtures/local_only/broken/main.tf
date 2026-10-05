terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

resource "local_file" "broken" {
  filename = "${path.module}/output.txt"
  content  = "this string is never closed
}
