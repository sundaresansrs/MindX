{ pkgs, ... }: {
  packages = [
    pkgs.python311
    pkgs.docker
    pkgs.docker-compose
  ];
  
  idx = {
    extensions = [
      "ms-python.python"
    ];
  };
}