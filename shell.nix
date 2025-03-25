# create environment with python
{pkgs ? import <nixpkgs> {}}:
pkgs.mkShell {
  buildInputs = with pkgs; [
    python312
    python312Packages.virtualenv
    python312Packages.pip
    python312Packages.pyyaml
    gcc
  ];
  shellHook = ''
     source venv/bin/activate
  '';
}
